import os
import time
from base64 import b64decode
from typing import Dict, List, Optional

import click
import yaml
import zulu
from click.shell_completion import CompletionItem
from tabulate import tabulate

import spyctl.cli as cli
import spyctl.config.configs as cfgs
import spyctl.spyctl_lib as lib
import spyctl.filter_resource as filt

SECRET_KIND = "APISecret"

SECRETS: Dict[str, "Secret"] = None


class InvalidSecretError(Exception):
    pass


class Secret:
    required_keys = {
        lib.API_FIELD,
        lib.KIND_FIELD,
        lib.METADATA_FIELD,
    }
    optional_keys = {lib.DATA_FIELD, lib.STRING_DATA_FIELD}

    def __init__(self, secret_data: Dict) -> None:
        if not isinstance(secret_data, dict):
            raise InvalidSecretError("Secret data is not a dictionary.")
        for key in self.required_keys:
            if key not in secret_data:
                raise InvalidSecretError(f"Secret missing {key} field.")
        if not lib.valid_api_version(secret_data.get(lib.API_FIELD)):
            raise InvalidSecretError("Invalid apiVersion.")
        if not lib.valid_kind(secret_data.get(lib.KIND_FIELD), SECRET_KIND):
            raise InvalidSecretError("Invalid kind.")
        self.metadata = secret_data.get(lib.METADATA_FIELD, {})
        if not isinstance(self.metadata, dict):
            raise InvalidSecretError("metadata is not a dictionary.")
        self.name = self.metadata.get(lib.METADATA_NAME_FIELD)
        if not self.name:
            raise InvalidSecretError("Invalid name")
        self.data = {}
        if lib.DATA_FIELD in secret_data:
            if not isinstance(secret_data[lib.DATA_FIELD], dict):
                raise InvalidSecretError(
                    f"{lib.DATA_FIELD} is not a dictionary"
                )
            self.data = secret_data[lib.DATA_FIELD]
        self.string_data = {}
        if lib.STRING_DATA_FIELD in secret_data:
            if not isinstance(secret_data[lib.STRING_DATA_FIELD], dict):
                raise InvalidSecretError(
                    f"{lib.STRING_DATA_FIELD} is not a dictionary"
                )
            self.string_data = secret_data[lib.STRING_DATA_FIELD]
        self.__validate_apisecret_data()

    def as_dict(self, creation_time=None) -> Dict:
        rv = {
            lib.API_FIELD: lib.API_VERSION,
            lib.KIND_FIELD: SECRET_KIND,
            lib.METADATA_FIELD: self.metadata,
        }
        if len(self.data) > 0:
            rv[lib.DATA_FIELD] = self.data
        if len(self.string_data) > 0:
            rv[lib.STRING_DATA_FIELD] = self.string_data
        if creation_time:
            rv[lib.METADATA_FIELD][lib.METADATA_CREATE_TIME] = creation_time
        return rv

    def get_credentials(self) -> Dict:
        rv = {}
        rv.update(self.__get_creds())
        return rv

    def __get_creds(self) -> Dict:
        if lib.API_KEY_FIELD in self.data:
            api_key = b64decode(self.data[lib.API_KEY_FIELD]).decode("ascii")
        else:
            api_key = self.string_data[lib.API_KEY_FIELD]
        if lib.API_URL_FIELD in self.data:
            api_url = b64decode(self.data[lib.API_URL_FIELD]).decode("ascii")
        else:
            api_url = self.string_data[lib.API_URL_FIELD]
        rv = {lib.API_KEY_FIELD: api_key, lib.API_URL_FIELD: api_url}
        return rv

    def __validate_apisecret_data(self):
        required_keys = [lib.API_KEY_FIELD, lib.API_URL_FIELD]
        for key in required_keys:
            in_data = False
            if key in self.data:
                if not isinstance(self.data[key], str):
                    raise InvalidSecretError(
                        f"Value for {key} must be a string"
                    )
                in_data = True
            in_string_data = False
            if key in self.string_data:
                if not isinstance(self.string_data[key], str):
                    raise InvalidSecretError(
                        f"Value for {key} must be a string"
                    )
                in_string_data = True
            if not in_data and not in_string_data:
                raise InvalidSecretError(f"{key} missing in data fields")
            elif in_data and in_string_data:
                cli.try_log(
                    f"Warning: {key} in multiple data fields. Defaulting to"
                    f" value in {lib.DATA_FIELD}"
                )


def load_secrets(silent=False):
    global SECRETS
    if SECRETS is None:
        SECRETS = {}
        loaded_files = lib.walk_up_tree(
            cfgs.GLOBAL_SECRETS_PATH, cfgs.LOCAL_SECRETS_PATH
        )
        # Reversed because more local files overwrite more global files
        for secrets_path, secrets_data in reversed(loaded_files):
            for secret_data in secrets_data:
                try:
                    secret = Secret(secret_data)
                    SECRETS[secret.name] = secret
                except InvalidSecretError as e:
                    if not silent:
                        cli.try_log(
                            f"{secrets_path} has an invalid secret."
                            f" {' '.join(e.args)}"
                        )


def set_secret(name: str, apiurl: str = None, apikey: str = None):
    global SECRETS
    updated = False
    if name in SECRETS:
        updated = True
        secret = SECRETS[name]
        if apikey and (
            not apiurl or apiurl == secret.string_data.get(lib.API_URL_FIELD)
        ):
            cli.try_log("Nothing to update.")
            return
        else:
            if apikey:
                secret.string_data[lib.API_KEY_FIELD] = apikey
            if apiurl:
                secret.string_data[lib.API_URL_FIELD] = apiurl
    else:
        if not apikey:
            cli.err_exit("Missing apikey.")
        new_secret = {
            lib.API_FIELD: lib.API_VERSION,
            lib.KIND_FIELD: SECRET_KIND,
            lib.METADATA_FIELD: {lib.METADATA_NAME_FIELD: name},
            lib.DATA_FIELD: {},
            lib.STRING_DATA_FIELD: {},
        }
        url = apiurl if apiurl else lib.DEFAULT_API_URL
        if not url:
            cli.err_exit("Invalid apiurl")
        new_secret[lib.STRING_DATA_FIELD] = {
            lib.API_KEY_FIELD: apikey,
            lib.API_URL_FIELD: url,
        }
        try:
            new_secret = Secret(new_secret)
        except InvalidSecretError as e:
            cli.err_exit(f"Invalid apisecret format. {' '.join(e.args)}")
        SECRETS[name] = new_secret
    output_data = []
    for s in SECRETS.values():
        output_data.append(s.as_dict(int(time.time())))
    try:
        with cfgs.GLOBAL_SECRETS_PATH.open("w") as f:
            try:
                yaml.dump(output_data, f, sort_keys=False)
                if updated:
                    cli.try_log(
                        "Updated apisecret"
                        f" '{name}' in {str(cfgs.GLOBAL_SECRETS_PATH)}"
                    )
                else:
                    cli.try_log(
                        "Created new apisecret"
                        f" '{name}' in {str(cfgs.GLOBAL_SECRETS_PATH)}"
                    )
            except yaml.YAMLError:
                cli.err_exit("Unable to write secrets to file, yaml error.")
    except Exception:
        cli.err_exit("Unable to write secrets to file. Check permissions.")


def delete_secret(secret_name: Dict):
    global SECRETS
    if secret_name not in SECRETS:
        cli.try_log(
            f"Unable to delete secret '{secret_name}'. Does not exist."
        )
        return
    if not cli.query_yes_no(
        f'Are you sure you want to delete the secret "{secret_name}"?'
    ):
        cli.try_log("Delete cancelled, exiting...")
        return
    del SECRETS[secret_name]
    output_data = []
    for s in SECRETS.values():
        output_data.append(s.as_dict())
    try:
        with cfgs.GLOBAL_SECRETS_PATH.open("w") as f:
            try:
                yaml.dump(output_data, f, sort_keys=False)
                cli.try_log(
                    f"Deleted secret"
                    f" '{secret_name}' from {str(cfgs.GLOBAL_SECRETS_PATH)}"
                )
            except yaml.YAMLError:
                cli.err_exit("Unable to write to secrets file, yaml error.")
    except Exception:
        cli.err_exit("Unable to write to secrets file. Check permissions.")


def handle_get_secrets(name, output):
    secrets = get_secrets()
    if name:
        secrets = filt.filter_obj(
            secrets, [f"{lib.METADATA_FIELD}.{lib.METADATA_NAME_FIELD}"], name
        )
    if output != lib.OUTPUT_DEFAULT:
        secrets = secrets_output(secrets)
    cli.show(secrets, output, {lib.OUTPUT_DEFAULT: secrets_summary_output})


def get_secrets():
    rv = []
    for secret in SECRETS.values():
        rv.append(secret.as_dict())
    return rv


def secrets_summary_output(secrets: List[Dict]):
    header = ["NAME", "DATA", "AGE"]
    data = []
    for secret in secrets:
        data.append(secret_summary_data(secret))
    return tabulate(data, header, tablefmt="plain")


def secret_summary_data(secret: Dict):
    creation_timestamp = secret[lib.METADATA_FIELD].get(
        lib.METADATA_CREATE_TIME
    )
    if creation_timestamp:
        creation_zulu = zulu.Zulu.fromtimestamp(creation_timestamp)
        age = f"{(zulu.now() - creation_zulu).days}d"
    else:
        age = "unknown"
    data_len = len(secret.get(lib.DATA_FIELD, [])) + len(
        secret.get(lib.STRING_DATA_FIELD, [])
    )
    rv = [
        secret[lib.METADATA_FIELD][lib.METADATA_NAME_FIELD],
        data_len,
        age,
    ]
    return rv


def secrets_output(secrets: List[Dict]):
    if len(secrets) == 1:
        return secrets[0]
    elif len(secrets) > 1:
        return {lib.API_FIELD: lib.API_VERSION, lib.ITEMS_FIELD: secrets}
    else:
        return


def find_secret(secret_name) -> Optional[Secret]:
    return SECRETS.get(secret_name)


class SecretsParam(click.ParamType):
    name = "secrets_param"

    def shell_complete(self, ctx, param, incomplete):
        load_secrets(silent=True)
        secrets = get_secrets()
        secret_names = [
            secret[lib.METADATA_FIELD][lib.METADATA_NAME_FIELD]
            for secret in secrets
        ]
        return [
            CompletionItem(secret_name)
            for secret_name in secret_names
            if secret_name.startswith(incomplete)
        ]

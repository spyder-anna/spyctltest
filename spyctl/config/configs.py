import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Iterable

import yaml
from tabulate import tabulate
from copy import deepcopy

import spyctl.api as api
import spyctl.cli as cli
import spyctl.config.secrets as s
import spyctl.spyctl_lib as lib

APP_NAME = "spyctl"
APP_DIR = f".{APP_NAME}"
APP_AUTHOR = "Spyderbat"
SECRETS_DIR = ".secrets"
GLOBAL_CONFIG_DIR = Path.joinpath(Path.home(), APP_DIR)
GLOBAL_SECRETS_DIR = Path.joinpath(GLOBAL_CONFIG_DIR, SECRETS_DIR)
CONFIG_FILENAME = "config"
SECRETS_FILENAME = "secrets"
GLOBAL_CONFIG_PATH = Path.joinpath(GLOBAL_CONFIG_DIR, CONFIG_FILENAME)
GLOBAL_SECRETS_PATH = Path.joinpath(GLOBAL_SECRETS_DIR, SECRETS_FILENAME)
LOCAL_CONFIG_PATH = Path.joinpath(Path.cwd(), APP_DIR, CONFIG_FILENAME)
LOCAL_SECRETS_PATH = Path(f".{APP_DIR}/{SECRETS_DIR}/{SECRETS_FILENAME}")
CURRENT_CONTEXT = None
LOADED_CONFIG: "Config" = None
# Pa
LOADED_CONFIGS: Dict[str, "Config"] = {}
CURR_CONTEXT_FIELD = "current-context"

# Config yaml required values
CONFIG_KIND = "Config"

# Config yaml fields
CONTEXTS_FIELD = "contexts"
CONTEXT_FIELD = "context"
CONTEXT_NAME_FIELD = "name"
SECRET_FIELD = "secret"
ORG_FIELD = lib.ORG_FIELD
POD_FIELD = lib.POD_FIELD
CLUSTER_FIELD = lib.CLUSTER_FIELD
NAMESPACE_FIELD = lib.NAMESPACE_FIELD
MACHINES_FIELD = lib.MACHINES_FIELD
CGROUP_FIELD = lib.CGROUP_FIELD
CONTAINER_NAME_FIELD = lib.CONT_NAME_FIELD
CONT_ID_FIELD = lib.CONT_ID_FIELD
IMG_FIELD = lib.IMAGE_FIELD
IMGID_FIELD = lib.IMAGEID_FIELD

CURR_CONTEXT_NONE = "__none__"
CONFIG_TEMPLATE = {
    lib.API_FIELD: lib.API_VERSION,
    lib.KIND_FIELD: CONFIG_KIND,
    CONTEXTS_FIELD: [],
    CURR_CONTEXT_FIELD: CURR_CONTEXT_NONE,
}


class InvalidContextDataError(Exception):
    pass


class InvalidConfigDataError(Exception):
    pass


class Context:
    required_keys = {CONTEXT_NAME_FIELD, CONTEXT_FIELD, SECRET_FIELD}
    required_context_keys = {ORG_FIELD}
    optional_context_keys = {
        CLUSTER_FIELD,
        NAMESPACE_FIELD,
        MACHINES_FIELD,
        POD_FIELD,
        CGROUP_FIELD,
        CONTAINER_NAME_FIELD,
        CONT_ID_FIELD,
        IMG_FIELD,
        IMGID_FIELD,
    }
    required_creds = {lib.API_KEY_FIELD, lib.API_URL_FIELD}

    def __init__(self, context_data: Dict) -> None:
        if not isinstance(context_data, dict):
            raise InvalidContextDataError("Context should be a dictionary.")
        for key in self.required_keys:
            if key not in context_data:
                raise InvalidContextDataError(f"Context missing {key} field.")
        self.context = context_data[CONTEXT_FIELD]
        if not isinstance(self.context, dict):
            raise InvalidContextDataError(
                "Context field of a context should be a dictionary."
            )
        for key in self.required_context_keys:
            if key not in self.context:
                raise InvalidContextDataError(f"Context missing {key} field.")
        for key in self.required_context_keys.union(
            self.optional_context_keys
        ):
            if key in self.context and not isinstance(self.context[key], str):
                raise InvalidContextDataError(
                    f"Value for {key} must be a string"
                )
        self.name = context_data[CONTEXT_NAME_FIELD]
        if not isinstance(self.name, str) or not self.name:
            raise InvalidContextDataError(
                "Context name is not a valid string."
            )
        self.secret_name = context_data[SECRET_FIELD]
        if not isinstance(self.secret_name, str):
            raise InvalidContextDataError(
                "Context secret is not a valid string."
            )
        self.secret = s.find_secret(self.secret_name)
        if self.secret is None:
            raise InvalidContextDataError(
                f"Unable to locate secret '{self.secret_name}'"
            )
        self.secret_creds = self.secret.get_credentials()
        for cred in self.required_creds:
            if cred not in self.secret_creds:
                raise InvalidContextDataError(
                    f"Credential '{cred}' not found in secret."
                )
            if not isinstance(self.secret_creds[cred], str):
                raise InvalidContextDataError(
                    f"Value for credential '{cred}' is not a string."
                )
        self.org_uid = None
        self.filters = {}
        self.__set_filters()

    def get_api_data(self) -> Tuple[str, str, str]:
        if (
            lib.API_KEY_FIELD not in self.secret_creds
            or lib.API_URL_FIELD not in self.secret_creds
        ):
            raise InvalidContextDataError
        api_url = self.secret_creds[lib.API_URL_FIELD]
        api_key = self.secret_creds[lib.API_KEY_FIELD]
        if self.org_uid is None:
            self.org_uid = validate_org(self.org, api_url, api_key)
        if self.org_uid is None:
            cli.err_exit(
                "Unable to validate organization name or ID."
                " Check context settings."
            )
        return (api_url, api_key, self.org_uid)

    def get_filters(self) -> Dict[str, List[str]]:
        return self.filters

    def as_dict(self) -> Dict:
        rv = {
            CONTEXT_NAME_FIELD: self.name,
            SECRET_FIELD: self.secret_name,
            CONTEXT_FIELD: self.context,
        }
        return rv

    def __set_filters(self):
        if len(self.filters) == 0:
            self.filters = self.context

    def __repr__(self) -> str:
        return f'Context("{self.name}", "{self.org}")'

    @property
    def org(self) -> str:
        return self.context[ORG_FIELD]


class Config:
    required_keys = {
        lib.API_FIELD,
        lib.KIND_FIELD,
        CONTEXTS_FIELD,
        CURR_CONTEXT_FIELD,
    }

    def __init__(
        self, config_data: Dict, config_path: Path, config_dir: Path
    ) -> None:
        self.config_path = config_path
        # config_dir identifies the location of the current workspace
        # is updated when more-local config files are merged in
        self.config_dir = config_dir
        for key in self.required_keys:
            if key not in config_data:
                raise InvalidConfigDataError(f"Config missing {key} field")
        if not lib.valid_api_version(config_data.get(lib.API_FIELD)):
            raise InvalidConfigDataError("Invalid apiVersion")
        if not lib.valid_kind(config_data.get(lib.KIND_FIELD), CONFIG_KIND):
            raise InvalidConfigDataError("Invalid kind")
        if not isinstance(config_data[CURR_CONTEXT_FIELD], str):
            raise InvalidConfigDataError(
                "Invalid current context, should be a string"
            )
        if not isinstance(config_data[CONTEXTS_FIELD], list):
            raise InvalidConfigDataError(
                f"Invalid {CONTEXTS_FIELD}, should be a list"
            )
        self.current_context = config_data[CURR_CONTEXT_FIELD]
        self.contexts: Dict[str, Context] = {}
        self.context_paths: Dict[str, str] = {}
        for context_data in config_data[CONTEXTS_FIELD]:
            context = Context(context_data)
            self.contexts[context.name] = context
            self.context_paths[context.name] = self.config_path

    def merge(self, new_config: "Config"):
        """Merges new_config into existing config overwriting data with
        matching keys

        Args:
            new_config (Config): a more-local config to merge into the
                current config.
        """
        for context_name, context in new_config.contexts.items():
            self.contexts[context_name] = context
            self.context_paths[context_name] = new_config.context_paths[
                context_name
            ]
        self.current_context = new_config.current_context
        self.config_dir = new_config.config_dir
        self.config_path = new_config.config_path

    def as_dict(self) -> Dict:
        rv = {
            lib.API_FIELD: lib.API_VERSION,
            lib.KIND_FIELD: CONFIG_KIND,
            CONTEXTS_FIELD: [
                context.as_dict() for context in self.contexts.values()
            ],
            CURR_CONTEXT_FIELD: self.current_context,
        }
        return rv


def load_config():
    """Loads spyctl configurations from disk starting with the current
    directory and ending with the global config. If no configuration
    file exists, the program exits.
    """
    if not GLOBAL_CONFIG_PATH.exists():
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        GLOBAL_CONFIG_PATH.touch()
        with GLOBAL_CONFIG_PATH.open("w") as f:
            yaml.dump(CONFIG_TEMPLATE, f)
    if not GLOBAL_SECRETS_PATH.exists():
        GLOBAL_SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        # GLOBAL_SECRETS_DIR.chmod(700)
        GLOBAL_SECRETS_PATH.touch()
        # GLOBAL_SECRETS_PATH.chmod(600)
    global LOADED_CONFIG, CURRENT_CONTEXT
    if LOADED_CONFIG is None:
        s.load_secrets()
        configs_data = lib.walk_up_tree(GLOBAL_CONFIG_PATH, LOCAL_CONFIG_PATH)
        configs: List[Config] = []
        seen = set()
        for config_path, config_data in configs_data:
            try:
                cfg = Config(config_data, config_path, config_path.parent)
                cfg_cpy = Config(
                    deepcopy(config_data), config_path, config_path.parent
                )
                configs.append(cfg)
                LOADED_CONFIGS[str(config_path)] = deepcopy(cfg_cpy)
            except InvalidConfigDataError as e:
                if str(config_path) not in seen:
                    cli.try_log(
                        f"Config at {str(config_path)} is invalid."
                        f" {' '.join(e.args)}"
                    )
            except InvalidContextDataError as e:
                if str(config_path) not in seen:
                    cli.try_log(
                        f"Config at {str(config_path)} has an invalid context."
                        f" {' '.join(e.args)}"
                    )
            seen.add(str(config_path))
        if len(configs) == 0:
            cli.try_log(
                "No valid configurations."
                " Clear or fix any invalid configuration files."
            )
        else:
            base_config = configs.pop()
            # Reversed so that most local config takes priority
            for config in reversed(configs):
                base_config.merge(config)
            if len(base_config.contexts) == 0:
                cli.try_log(
                    "No valid contexts. Try using 'spyctl config"
                    " set-context'."
                )
            elif (
                base_config.current_context == CURR_CONTEXT_NONE
                or not base_config.current_context
            ):
                cli.try_log(
                    "Current context is not set. Try using"
                    " 'spyctl config use-context'"
                )
            elif base_config.current_context not in base_config.contexts:
                cli.try_log(
                    "Unable to locate current context"
                    f" '{base_config.current_context}'."
                    " Try using 'spyctl config use-context'."
                )
            LOADED_CONFIG = base_config
            CURRENT_CONTEXT = base_config.contexts.get(
                base_config.current_context
            )


def get_loaded_config() -> Optional[Config]:
    return LOADED_CONFIG


def get_current_context() -> Context:
    if CURRENT_CONTEXT is None:
        cli.err_exit("No current context set")
    return CURRENT_CONTEXT


def init():
    perform_init = False
    reset = False
    if LOCAL_CONFIG_PATH.exists() and LOCAL_CONFIG_PATH == GLOBAL_CONFIG_PATH:
        if cli.query_yes_no(
            "Are you sure you want to reset the global spyctl configuration"
            f" file '{str(LOCAL_CONFIG_PATH)}'",
            "no",
        ):
            perform_init = True
            reset = True
    elif LOCAL_CONFIG_PATH.exists():
        if cli.query_yes_no(
            "A spyctl configuration file already exists at"
            f" '{str(LOCAL_CONFIG_PATH)}'. Are you sure you want to reset it?",
            "no",
        ):
            reset = True
            perform_init = True
    else:
        perform_init = True
    if perform_init:
        LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOCAL_CONFIG_PATH.open("w") as f:
            yaml.dump(CONFIG_TEMPLATE, f)
        cli.try_log(
            f"{'Reset' if reset else 'Created'} configuration file at"
            f" {str(LOCAL_CONFIG_PATH)}."
        )


def set_context(
    name, secret, force_global: bool, use_context: bool, **context
):
    global LOADED_CONFIGS
    new_context = {
        CONTEXT_NAME_FIELD: name,
        SECRET_FIELD: secret,
        CONTEXT_FIELD: context,
    }
    try:
        new_context = Context(new_context)
    except InvalidContextDataError as e:
        cli.err_exit(f"Unable to set context. {' '.join(e.args)}")
    config = get_loaded_config()
    if config is None:
        return
    updated = name in config.contexts
    if force_global:
        # global flag was set so update/set context at the global level
        context_path = GLOBAL_CONFIG_PATH
    else:
        if updated:
            # update the context at the file of the existing context
            context_path = config.context_paths[name]
        else:
            # set the context at the most-local configuration file
            context_path = config.config_path
    target_config = LOADED_CONFIGS[str(context_path)]
    tgt_updated_curr_ctx = False
    if len(target_config.contexts) == 0:
        target_config.current_context = name
        tgt_updated_curr_ctx = True
    # We want to ensure the current-context of the local configuration
    # file has been set. local config can be the same as target or not,
    # but it is the configuration file closest to the user's cwd
    local_config = LOADED_CONFIGS[str(config.config_path)]
    local_updated_curr_ctx = False
    if (
        len(config.contexts) == 0
        and len(local_config.contexts) == 0
        and local_config.config_path != context_path
    ) or use_context:
        local_updated_curr_ctx = True
        local_config.current_context = name
    target_config.contexts[name] = new_context
    target_config.context_paths[name] = config.config_path
    try:
        with context_path.open("w") as f:
            yaml.dump(target_config.as_dict(), f, sort_keys=False)
            cli.try_log(
                f"{'Updated' if updated else 'Set new'} context '{name}' in"
                f" configuration file '{context_path}'."
            )
            if tgt_updated_curr_ctx:
                cli.try_log(
                    f"Updated current context to '{name}' in"
                    f" configuration file '{context_path}'."
                )
        if local_updated_curr_ctx:
            with local_config.config_path.open("w") as f:
                yaml.dump(local_config.as_dict(), f, sort_keys=False)
                if (
                    local_config.config_path != context_path
                    or not tgt_updated_curr_ctx
                ):
                    cli.try_log(
                        f"Updated current context to '{name}' in"
                        f" configuration file '{local_config.config_path}'."
                    )
    except Exception as e:
        cli.err_exit(f"Unable to set context. {' '.join(e.args)}")


def delete_context(name, force_global):
    global LOADED_CONFIGS
    config = get_loaded_config()
    if config is None:
        return
    if config is None:
        cli.try_log("No valid configuration found")
        return
    if force_global:
        # global flag was set so delete context at the global level
        context_path = GLOBAL_CONFIG_PATH
    else:
        # delete the context in the file where it resides
        context_path = config.context_paths[name]
    target_config = LOADED_CONFIGS[str(context_path)]
    if name not in target_config.contexts:
        cli.try_log(
            f"Unable to delete context '{name}' from {str(context_path)}."
            " Context does not exist."
        )
        return
    del target_config.contexts[name]
    updated_curr_context = False
    if target_config.current_context == name:
        if len(target_config.contexts) > 0:
            fallback_context = next(iter(target_config.contexts.values()))
            target_config.current_context = fallback_context.name
            updated_curr_context = True
        elif len(config.contexts) > 0:
            fallback_context = next(iter(config.contexts.values()))
            target_config.current_context = fallback_context.name
            updated_curr_context = True
        else:
            target_config.current_context = CURR_CONTEXT_NONE
    try:
        with context_path.open("w") as f:
            yaml.dump(target_config.as_dict(), f, sort_keys=False)
            cli.try_log(
                f"Deleted context '{name}' in"
                f" configuration file '{context_path}'."
            )
            if updated_curr_context:
                cli.try_log(
                    f"Current context at {target_config.config_path} deleted."
                    " Updating to fallback context"
                    f" '{target_config.current_context}'."
                )
            if len(config.contexts) == 0:
                cli.try_log(
                    "Configuration has no contexts. Use 'spyctl config"
                    " set-context' to add one."
                )
    except Exception as e:
        cli.err_exit(f"Unable to delete context. {' '.join(e.args)}")


def current_context(force_global):
    global LOADED_CONFIGS
    config = get_loaded_config()
    if config is None:
        return
    if force_global:
        config = LOADED_CONFIGS[str(GLOBAL_CONFIG_PATH)]
    if (
        config.current_context == CURR_CONTEXT_NONE
        or not config.current_context
    ):
        if len(config.contexts) > 0:
            cli.try_log(
                "No current context. Use 'spyctl config use-context' to set"
                " one."
            )
        elif len(config.contexts) > 0:
            cli.try_log(
                "No current context. Use 'spyctl config set-context' to create"
                " and set one."
            )
    else:
        headers = ["Context Name", "Configuration File", "Context Location"]
        ctx_loc = str(config.context_paths.get(config.current_context))
        if ctx_loc == "None":
            ctx_loc = "Missing"
        curr_path = str(config.config_path)
        data = [
            [
                config.current_context,
                curr_path,
                "Same as Config File" if ctx_loc == curr_path else ctx_loc,
            ]
        ]
        print(tabulate(data, headers, tablefmt="plain"))


def use_context(name, force_global):
    global LOADED_CONFIGS
    config = get_loaded_config()
    if config is None:
        return
    found = name in config.contexts
    if not found:
        cli.try_log(
            f"Unable to set current context '{name}' for {str(context_path)}."
            " Context does not exist."
        )
        return
    if force_global:
        # global flag was set so update/set context at the global level
        context_path = GLOBAL_CONFIG_PATH
    else:
        # update the current context in the local configuration file
        context_path = config.config_path
    target_config = LOADED_CONFIGS[str(context_path)]
    target_config.current_context = name
    try:
        with context_path.open("w") as f:
            yaml.dump(target_config.as_dict(), f, sort_keys=False)
            cli.try_log(
                f"Set current context to '{name}' in"
                f" configuration file '{context_path}'."
            )
    except Exception as e:
        cli.err_exit(f"Unable to delete context. {' '.join(e.args)}")


def view_config(force_global, force_workspace, output):
    global LOADED_CONFIGS
    config = get_loaded_config()
    if config is None:
        return
    if force_global:
        # global flag was set so update/set context at the global level
        cfg_to_view = LOADED_CONFIGS[str(GLOBAL_CONFIG_PATH)].as_dict()
    elif force_workspace:
        cfg_to_view = LOADED_CONFIGS[str(config.config_path)].as_dict()
    else:
        cfg_to_view = config.as_dict()
    if output == lib.OUTPUT_DEFAULT:
        output = lib.OUTPUT_YAML
    cli.show(cfg_to_view, output)


def validate_org(org, api_url, api_key) -> Optional[str]:
    orgs = api.get_orgs(api_url, api_key, cli.api_err_exit)
    if orgs is not None:
        for uid, name in zip(*orgs):
            if org == name or org == uid:
                if name == "Defend The Flag":
                    cli.err_exit("invalid organization")
                return uid
    return None

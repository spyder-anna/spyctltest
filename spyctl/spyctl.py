#! /usr/bin/env python3

import time
from typing import Dict, List

import click

import spyctl.config.configs as cfgs
import spyctl.config.secrets as s
import spyctl.spyctl_lib as lib
import spyctl.commands.get as g
import spyctl.commands.create as c
import spyctl.commands.merge as m
import spyctl.commands.diff as d
import spyctl.cli as cli
from spyctl.commands.apply import handle_apply
from spyctl.commands.delete import handle_delete

MAIN_EPILOG = (
    'Use "spyctl <command> --help" for more information about a given command'
)
DEFAULT_START_TIME = 1614811600

# ----------------------------------------------------------------- #
#                     Command Tree Entrypoint                       #
# ----------------------------------------------------------------- #


@click.group(cls=lib.CustomGroup, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.version_option(None, "-v", "--version", prog_name="Spyctl", hidden=True)
@click.pass_context
def main(ctx: click.Context):
    """spyctl displays and controls resources within your Spyderbat
    environment
    """
    cfgs.load_config()


# ----------------------------------------------------------------- #
#                         Apply Subcommand                          #
# ----------------------------------------------------------------- #


@main.command("apply", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True, is_eager=True)
@click.option(
    "-f",
    "--filename",
    help="Filename containing Spyderbat resource.",
    metavar="",
    type=click.File(),
)
def apply(filename):
    """Apply a configuration to a resource by file name."""
    handle_apply(filename)


# ----------------------------------------------------------------- #
#                         Config Subcommand                         #
# ----------------------------------------------------------------- #


@main.group("config", cls=lib.CustomSubGroup, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.pass_context
def config(ctx: click.Context):
    """Modify spyctl config files."""


@config.command("delete-context", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
@click.option(
    "-y",
    "--yes",
    "--assume-yes",
    is_flag=True,
    help='Automatic yes to prompts; assume "yes" as answer to all prompts and'
    " run non-interactively.",
)
@click.argument("name")
def delete_context(name, force_global, yes=False):
    """Delete the specified context from a spyctl configuration file."""
    if yes:
        cli.set_yes_option()
    cfgs.delete_context(name, force_global)


@config.command("delete-apisecret", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-y",
    "--yes",
    "--assume-yes",
    is_flag=True,
    help='Automatic yes to prompts; assume "yes" as answer to all prompts and'
    " run non-interactively.",
)
@click.argument("name", type=s.SecretsParam())
def delete_apisecret(name, yes=False):
    """Delete the specified context from a spyctl configuration file."""
    if yes:
        cli.set_yes_option()
    s.delete_secret(name)


@config.command("current-context", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
def current_context(force_global):
    """Display the current-context."""
    cfgs.current_context(force_global)


@config.command("get-contexts", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.argument("name", required=False, type=cfgs.ContextsParam())
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(
        [lib.OUTPUT_DEFAULT, lib.OUTPUT_WIDE], case_sensitive=False
    ),
)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
def get_contexts(force_global, output, name=None):
    """Describe one or many contexts"""
    cfgs.get_contexts(name, force_global, output)


@config.command("get-apisecrets", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.argument("name", required=False, type=s.SecretsParam())
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(
        lib.OUTPUT_CHOICES + [lib.OUTPUT_WIDE], case_sensitive=False
    ),
)
def get_api_secrets(output, name=None):
    """Describe one or many apisecrets"""
    s.handle_get_secrets(name, output)


@config.command("set-context", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
@click.option(
    "-u",
    "--use-context",
    "use_ctx",
    is_flag=True,
    help="Use this context when set. Sets the current-context field in the"
    " config file. The first context added to a config is automatically set as"
    " current-context.",
)
@click.option(
    "-s",
    "--secret",
    help="Name of api config secret.",
    metavar="",
    required=True,
    type=s.SecretsParam(),
)
@click.option(
    "-o",
    "--organization",
    "--org",
    help="ID or name of Spyderbat organization.",
    metavar="",
    required=True,
)
@click.option(
    "-c",
    "--cluster",
    help="Name or Spyderbat ID of Kubernetes cluster.",
    metavar="",
)
@click.option(
    "-n",
    "--namespace",
    help="Name or Spyderbat ID of Kubernetes namespace.",
    metavar="",
)
@click.option(
    "-p", "--pod", help="Name or Spyderbat ID of Kubernetes pod.", metavar=""
)
@click.option(
    "-m",
    "--machines",
    help="Name of machine group, or name or Spyderbat ID of a machine (node).",
    metavar="",
)
@click.option(
    "-i",
    "--image",
    help="Name of container image, wildcards allowed.",
    metavar="",
)
@click.option("-d", "--image-id", help="Container image ID.", metavar="")
@click.option(
    "-N", "--container-name", help="Name of specific container.", metavar=""
)
@click.option("-C", "--cgroup", help="Linux service cgroup.", metavar="")
@click.argument("name")
def set_context(name, secret, force_global, use_ctx, **context):
    """Set a context entry in a spyctl configuration file, or update an
    existing one.
    """
    context = {
        key: value for key, value in context.items() if value is not None
    }
    cfgs.set_context(name, secret, force_global, use_ctx, **context)


@config.command("set-apisecret", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.argument("name", required=False)
@click.option(
    "-k",
    "--apikey",
    "--api-key",
    "api_key",
    help="API key generated via the Spyderbat UI",
    metavar="",
)
@click.option(
    "-u",
    "--apiurl",
    "--api-url",
    "api_url",
    help=f"URL target for api queries. Default: {lib.DEFAULT_API_URL}",
    metavar="",
)
def set_apisecrets(api_key=None, api_url=None, name=None):
    """
    Set a new entry in the spyctl secrets file, or update an existing one.
    """
    s.set_secret(name, api_url, api_key)


@config.command("use-context", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
@click.argument("name", type=cfgs.ContextsParam())
def use_context(name, force_global):
    """Set the current-context in a spyctl configuration file."""
    cfgs.use_context(name, force_global)


@config.command("view", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-g",
    "--global",
    "force_global",
    is_flag=True,
    help="When operating within a spyctl workspace, this forces a change to"
    " the global spyctl config.",
)
@click.option(
    "-w",
    "--workspace",
    "force_workspace",
    is_flag=True,
    help="View merged configuration file. Supply a flag to view global"
    " configuration file or local workspace configuration file.",
)
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(lib.OUTPUT_CHOICES, case_sensitive=False),
)
def view(force_global, force_workspace, output):
    """View the current spyctl configuration file(s)."""
    cfgs.view_config(force_global, force_workspace, output)


# ----------------------------------------------------------------- #
#                         Create Subcommand                         #
# ----------------------------------------------------------------- #


@main.group("create", cls=lib.CustomSubGroup, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
def create():
    """Create a resource from a file."""
    pass


@create.command("baseline", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-f",
    "--from-file",
    "filename",
    help="File that contains the FingerprintsGroup object, from which spyctl"
    " creates a baseline.",
    metavar="",
    type=click.File(),
)
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(lib.OUTPUT_CHOICES, case_sensitive=False),
)
def create_baseline(filename, output):
    """Create a Baseline from a file, outputted to stdout"""
    c.handle_create_baseline(filename, output)


@create.command("policy", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-f",
    "--from-file",
    "filename",
    help="File that contains the FingerprintsGroup or SpyderbatBaseline"
    " object, from which spyctl creates a policy",
    metavar="",
    type=click.File(),
)
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(lib.OUTPUT_CHOICES, case_sensitive=False),
)
def create_policy(filename, output):
    """Create a Policy object from a file, outputted to stdout"""
    c.handle_create_policy(filename, output)


# ----------------------------------------------------------------- #
#                        Delete Subcommand                          #
# ----------------------------------------------------------------- #


@main.command("delete", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.argument("resource", type=lib.DelResourcesParam())
@click.argument("name_or_id")
@click.option(
    "-y",
    "--yes",
    "--assume-yes",
    is_flag=True,
    help='Automatic yes to prompts; assume "yes" as answer to all prompts and'
    " run non-interactively.",
)
def delete(resource, name_or_id, yes=False):
    """Delete resources by resource and names, or by resource and ids"""
    if yes:
        cli.set_yes_option()
    handle_delete(resource, name_or_id)


# ----------------------------------------------------------------- #
#                          Diff Subcommand                          #
# ----------------------------------------------------------------- #


@main.command("diff", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-f",
    "--filename",
    help="Target file of the diff.",
    metavar="",
    type=click.File(),
)
@click.option(
    "-w",
    "--with-file",
    help="File to diff with target file.",
    metavar="",
    type=click.File(),
)
@click.option(
    "-l",
    "--latest",
    is_flag=True,
    help="Diff file with latest records using the value of lastTimestamp in"
    " metadata",
    metavar="",
)
def diff(filename, with_file=None, latest=False):
    """Diff FingerprintsGroups with SpyderbatBaselines and SpyderbatPolicies"""
    d.handle_diff(filename, with_file, latest)


# ----------------------------------------------------------------- #
#                          Get Subcommand                           #
# ----------------------------------------------------------------- #


@main.group("get", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.argument("resource", type=lib.GetResourcesParam())
@click.argument("name_or_id", required=False)
@click.option(
    "--image",
    cfgs.IMG_FIELD,
    help="Only show resources tied to this container image."
    " Overrides value current context if it exists.",
)
@click.option(
    "--image-id",
    cfgs.IMGID_FIELD,
    help="Only show resources tied to containers running with this"
    " image id. Overrides value current context if it exists.",
)
@click.option(
    "--container-name",
    cfgs.CONTAINER_NAME_FIELD,
    help="Only show resources tied to containers running with this"
    " container name. Overrides value current context if it exists.",
)
@click.option(
    "--container-id",
    cfgs.CONT_ID_FIELD,
    help="Only show resources tied to containers running with this"
    " container id. Overrides value current context if it exists.",
)
@click.option(
    "--cgroup",
    cfgs.CGROUP_FIELD,
    help="Only show resources tied to machines running Linux services with"
    " this cgroup. Overrides value current context if it exists.",
)
@click.option(
    "--pod",
    cfgs.POD_FIELD,
    help="Only show resources tied to this pod uid."
    " Overrides value current context if it exists.",
)
@click.option(
    f"--{cfgs.MACHINES_FIELD}",
    "--nodes",
    help="Only show resources to these nodes."
    " Overrides value current context if it exists.",
)
@click.option(
    f"--{cfgs.NAMESPACE_FIELD}",
    help="Only show resources tied to this namespace."
    " Overrides value current context if it exists.",
)
@click.option(
    f"--{cfgs.CLUSTER_FIELD}",
    help="Only show resources tied to this cluster."
    " Overrides value current context if it exists.",
)
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(lib.OUTPUT_CHOICES, case_sensitive=False),
)
@click.option(
    "-f",
    "--filename",
    help="Input file to create filters from. Used if you want to get resources"
    " directly related to another resource. E.g. the Fingerprint Groups for a"
    " given Baseline file.",
    metavar="",
    type=click.File(),
)
@click.option(
    "-l",
    "--latest",
    help="Starting time of the query is set to the"
    f" {lib.LATEST_TIMESTAMP_FIELD}"
    f" field the input resource's {lib.METADATA_FIELD}."
    " [Requires '--filename' option to be set]",
    is_flag=True,
)
@click.option(
    "-E",
    "--exact",
    "--exact-match",
    is_flag=True,
    help="Exact match for name or ID.",
)
@click.option(
    "-t",
    "--start-time",
    "st",
    help="Start time of the query. Default is 24 hours ago.",
    default="24h",
    type=lib.time_inp,
)
@click.option(
    "-e",
    "--end-time",
    "et",
    help="End time of the query. Default is now.",
    default=time.time(),
    type=lib.time_inp,
)
def get(
    resource,
    st,
    et,
    output,
    filename=None,
    exact=False,
    name_or_id=None,
    latest=None,
    **filters,
):
    """Display one or many resources."""
    filters = {
        key: value for key, value in filters.items() if value is not None
    }
    g.handle_get(
        resource,
        name_or_id,
        st,
        et,
        filename,
        latest,
        exact,
        output,
        **filters,
    )


# ----------------------------------------------------------------- #
#                         Init Subcommand                           #
# ----------------------------------------------------------------- #


@main.command("init", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
def init():
    """Initialize a workspace"""
    cfgs.init()


# ----------------------------------------------------------------- #
#                         Merge Subcommand                          #
# ----------------------------------------------------------------- #


@main.command("merge", cls=lib.CustomCommand, epilog=MAIN_EPILOG)
@click.help_option("-h", "--help", hidden=True)
@click.option(
    "-f",
    "--filename",
    help="Target file of the merge.",
    metavar="",
    required=True,
    type=click.File(),
)
@click.option(
    "-w",
    "--with-file",
    help="File to merge into target file.",
    metavar="",
    type=click.File(),
)
@click.option(
    "-l",
    "--latest",
    is_flag=True,
    help=f"Merge file with latest records using the value of"
    f" {lib.LATEST_TIMESTAMP_FIELD} in the input file's metadata",
    metavar="",
)
@click.option(
    "-o",
    "--output",
    default=lib.OUTPUT_DEFAULT,
    type=click.Choice(lib.OUTPUT_CHOICES, case_sensitive=False),
)
def merge(filename, output, with_file=None, latest=False):
    """Merge FingerprintsGroups into SpyderbatBaselines and
    SpyderbatPolicies
    """
    if output == lib.OUTPUT_DEFAULT:
        output = lib.OUTPUT_YAML
    m.handle_merge(filename, with_file, latest, output)


if __name__ == "__main__":
    main()

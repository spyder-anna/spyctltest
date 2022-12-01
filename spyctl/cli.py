import json
import os
import sys
import time
from typing import Callable, Dict, List

import yaml

import spyctl.policies as policy
import spyctl.user_config as u_conf
import spyctl.api as api
from spyctl.args import OUTPUT_JSON, OUTPUT_YAML
from spyctl.fingerprints import Fingerprint

yaml.Dumper.ignore_aliases = lambda *args: True


def try_log(*args, **kwargs):
    try:
        print(*args, **kwargs, file=sys.stderr)
        sys.stderr.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stderr.fileno())
        sys.exit(1)


def try_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
        sys.stdout.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write(
                "Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n"
            )


def contains(obj, filt):
    filt_str = filt.split("=")
    keys = []
    if len(filt_str) > 1:
        keys = filt_str[0].split(".")
    val_str = filt_str[-1]

    def cont_keys(obj, keys):
        if isinstance(obj, dict):
            # returns false if it doesn't have the key
            for key, val in obj.items():
                if len(keys) > 0 and keys[0] != key:
                    continue
                if cont_keys(val, keys[1:]):
                    return True
            return False
        elif isinstance(obj, str):
            return val_str in obj
        return True

    return cont_keys(obj, keys)


def try_filter(obj, filt):
    if isinstance(obj, dict):
        remove = []
        for key, val in obj.items():
            try_filter(val, filt)
            if len(val) == 0:
                remove.append(key)
        for key in remove:
            del obj[key]
    elif isinstance(obj, list):
        remove = []
        for i, item in enumerate(obj):
            if not contains(item, filt):
                remove.append(i)
        removed = 0
        for i in remove:
            del obj[i - removed]
            removed += 1


def show(obj, args, alternative_outputs: Dict[str, Callable] = {}):
    for filt in args.filter:
        try_filter(obj, filt)
    if args.output == OUTPUT_YAML:
        try_print(yaml.dump(obj, sort_keys=False), end="")
    elif args.output == OUTPUT_JSON:
        try_print(json.dumps(obj, sort_keys=False, indent=2))
    elif args.output in alternative_outputs:
        try_print(alternative_outputs[args.output](obj), end="")


def read_stdin():
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def get_open_input(string: str):
    if string == "-":
        return read_stdin().strip('"')
    if os.path.exists(string):
        with open(string, "r") as f:
            return f.read().strip().strip('"')
    return string


def handle_list(list_string: str, obj_to_str=None) -> List[str]:
    try:
        objs = None
        try:
            objs = json.loads(list_string)
        except json.JSONDecodeError:
            objs = yaml.load(list_string, yaml.Loader)
            if isinstance(objs, str):
                raise ValueError
        if obj_to_str is not None:
            ret = []
            if isinstance(objs, dict):
                objs = [obj for obj in objs.values()]
            for obj in objs:
                string = obj_to_str(obj)
                if isinstance(string, list):
                    ret.extend(string)
                else:
                    ret.append(string)
            return ret
        return objs
    except Exception:
        return [s.strip().strip('"') for s in list_string.split(",")]


def time_input(args):
    if args.within:
        tup = args.within, int(time.time())
        return tup
    elif args.time_range:
        if args.time_range[1] < args.time_range[0]:
            err_exit("start time was before end time")
        return tuple(args.time_range)
    else:
        t = args.time if args.time else time.time()
        return t, t


def err_exit(message: str):
    sys.stderr.write(f"Error: {message}\n")
    exit(1)


def api_err_exit(error_code, reason, *msg):
    title = f"{error_code} ({reason}) error while fetching data"
    if msg is not None:
        title += ". " + " ".join(msg)
    err_exit(title)


def clusters_input(args):
    inp = get_open_input(args.clusters)

    def get_uid(clust_obj):
        if "uid" in clust_obj:
            return clust_obj["uid"]
        else:
            err_exit("cluster object input was missing 'uid'")

    names_or_uids = handle_list(inp, get_uid)
    names, uids = api.get_clusters(*u_conf.read_config(), api_err_exit)
    clusters = []
    for string in names_or_uids:
        found = False
        for name, uid in zip(names, uids):
            if string == uid or string == name:
                clusters.append({"name": name, "uid": uid})
                found = True
                break
        if not found:
            err_exit(
                f"cluster '{string}' did not exist in specified organization"
            )
    clusters.sort(key=lambda c: c["name"])
    return clusters


def machines_input(args):
    inp = get_open_input(args.machines)

    def get_muid(mach):
        if isinstance(mach, list):
            return [get_muid(m) for m in mach]
        elif "muid" in mach:
            return mach["muid"]
        else:
            err_exit("machine object was missing 'muid'")

    names_or_uids = handle_list(inp, get_muid)
    muids, names = api.get_muids(
        *u_conf.read_config(), time_input(args), api_err_exit
    )
    machs = []
    for string in names_or_uids:
        found = False
        for name, muid in zip(names, muids):
            if string == muid or string == name:
                machs.append({"name": name, "muid": muid})
                found = True
                break
        if not found:
            err_exit(
                f"machine '{string}' did not exist in specified organization"
            )
    machs.sort(key=lambda m: m["name"])
    return machs


def pods_input(args):
    inp = get_open_input(args.pods)

    def get_uid(pod_obj):
        if isinstance(pod_obj, list):
            return [get_uid(p) for p in pod_obj]
        elif "uid" in pod_obj:
            return pod_obj["uid"]
        else:
            ret = []
            for sub in pod_obj.values():
                if not isinstance(sub, list):
                    err_exit("pod object was missing 'uid'")
                ret.extend(get_uid(sub))
            return ret

    names_or_uids = handle_list(inp, get_uid)
    _, clus_uids = api.get_clusters(*u_conf.read_config(), api_err_exit)
    pods = []
    all_pods = ([], [], [])
    for clus_uid in clus_uids:
        pod_dict = api.get_clust_pods(
            *u_conf.read_config(), clus_uid, time_input(args), api_err_exit
        )
        for list_tup in pod_dict.values():
            for i in range(len(all_pods)):
                all_pods[i].extend(list_tup[i])
    for string in names_or_uids:
        found = False
        for name, uid, muid in zip(*all_pods):
            if string == name or string == uid:
                pods.append({"name": name, "uid": uid, "muid": muid})
                found = True
                break
        if not found:
            try_log(f"pod '{string}' did not exist in specified organization")
    pods.sort(key=lambda p: p["name"])
    return pods


def fingerprint_input(files: List) -> List[Fingerprint]:
    fingerprints = []

    def load_fprint(string):
        try:
            obj = yaml.load(string, yaml.Loader)
            if isinstance(obj, list):
                for o in obj:
                    fingerprints.append(Fingerprint(o))
            else:
                fingerprints.append(Fingerprint(obj))
        except yaml.YAMLError:
            err_exit("invalid yaml input")
        except KeyError as err:
            (key,) = err.args
            err_exit(f"fingerprint was missing key '{key}'")

    if len(files) == 0:
        inp = read_stdin()
        load_fprint(inp)
    else:
        for file in files:
            load_fprint(file.read())
    return fingerprints


def policy_input(files: List) -> List[policy.Policy]:
    policies = []

    def load_pols(string):
        try:
            obj = yaml.load(string, yaml.Loader)
            if isinstance(obj, list):
                for o in obj:
                    pol_type = o[policy.K8S_METADATA_FIELD][
                        policy.METADATA_TYPE_FIELD
                    ]
                    policies.append(policy.Policy(pol_type))
            else:
                pol_type = obj[policy.K8S_METADATA_FIELD][
                    policy.METADATA_TYPE_FIELD
                ]
                policies.append(policy.Policy(pol_type, obj))
        except yaml.YAMLError:
            err_exit("invalid yaml input")
        except KeyError as err:
            (key,) = err.args
            err_exit(f"policy was missing key '{key}'")

    if len(files) == 0:
        inp = read_stdin()
        load_pols(inp)
    else:
        for file in files:
            try:
                load_pols(file.read())
            except IOError:
                try_log(f"Unable to read file {file}")
                continue
            except Exception:
                continue
    return policies


def namespaces_input(args):
    inp = get_open_input(args.namespaces)

    def get_strings(namespace):
        if isinstance(namespace, list):
            return [get_strings(n) for n in namespace]
        else:
            return namespace

    return sorted(handle_list(inp, get_strings))

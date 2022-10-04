from curses import meta
from distutils.file_util import copy_file
from typing import Dict, List, Union
import yaml

from merge import MergeDumper

from simple_term_menu import TerminalMenu


class Fingerprint():
    def __init__(self, fprint) -> None:
        self.fprint = fprint
        self.suppr_str = ""
        self.calc_lengths()
        # still getting fingerprints from the api without metadata for now
        if 'metadata' not in self.fprint:
            meta_keys = [
                ('checksum', 'checksum'),
                ('muid', 'muid'),
                ('name', 'service_name'),
                ('root', 'root_puid')
            ]
            meta = dict()
            for key in meta_keys:
                if key[1] in self.fprint:
                    meta[key[0]] = self.fprint[key[1]]
            self.fprint['metadata'] = meta
            import pdb; pdb.set_trace()
    
    @property
    def metadata(self):
        return self.fprint['metadata']
    
    def get_id(self):
        return self.fprint.get('id')
    
    def preview_str(self):
        fprint_yaml = yaml.dump(dict(spec=self.fprint['spec']), sort_keys=False)
        return f"{self.metadata['name']}{self.suppr_str} --" + \
        f" proc_nodes: {self.fprint['proc_fprint_len']}," + \
        f" ingress_nodes: {self.fprint['ingress_len']}," + \
        f" egress_nodes: {self.fprint['egress_len']} |" + \
        f" {fprint_yaml}"
    
    def get_output(self):
        copy_fields = ['spec', 'metadata', 'kind', 'apiVersion']
        rv = dict()
        for key in copy_fields:
            if key in self.fprint:
                rv[key] = self.fprint[key]
        return rv
    
    def set_num_suppressed(self, num: int):
        self.suppr_str = f" ({num} suppressed)"
    
    def calc_lengths(self):
        proc_fprint_len = 0
        node_queue = self.fprint['spec']['processPolicy'].copy()
        for node in node_queue:
            proc_fprint_len += 1
            if 'children' in node:
                node_queue += node['children']
        ingress_len = len(self.fprint['spec']['networkPolicy']['ingress'])
        egress_len = len(self.fprint['spec']['networkPolicy']['egress'])
        self.fprint['proc_fprint_len'] = proc_fprint_len
        self.fprint['ingress_len'] = ingress_len
        self.fprint['egress_len'] = egress_len
    
    @staticmethod
    def prepare_many(objs: List) -> List:
        latest: Dict[str, Fingerprint] = {}
        # keep only the latest fingerprints with the same id
        # can only filter out fingerprints that have ids, aka directly from the api
        ex_n = 0
        obj: Fingerprint
        for obj in objs:
            f_id = obj.get_id()
            if f_id is None:
                latest[ex_n] = obj
                ex_n += 1
                continue
            if f_id not in latest:
                latest[f_id] = obj
            elif latest[f_id].fprint['time'] < obj.fprint['time']:
                latest[f_id] = obj
        checksums = {}
        for obj in latest.values():
            checksum = obj.metadata['checksum']
            if checksum not in checksums:
                checksums[checksum] = {
                    'print': obj,
                    'suppressed': 0
                }
            else:
                entry = checksums[checksum]
                entry['suppressed'] += 1
                obj.set_num_suppressed(entry['suppressed'])
                entry['print'] = obj
        rv = [val['print'] for val in checksums.values()]
        rv.sort(key=lambda f: f.preview_str())
        return rv


def dialog(title):
    index = TerminalMenu(
        ['[Y] Yes', '[N] No'],
        title=title
    ).show()
    return index == 0


def save_service_fingerprint_yaml(fingerprints: List[Fingerprint]):
    save_options = [
        "[1] Save individual file(s) (for editing & uploading)",
        "[2] Save in one file (for viewing)",
        "[3] Back"
    ]
    index = TerminalMenu(
        save_options,
        title="Select an option:"
    ).show() if len(fingerprints) > 1 else 0
    if index is None or index == 2:
        return
    if index == 0:
        for fprint in fingerprints:
            if dialog(f"Save fingerprint for {fprint.metadata['name']}?"):
                while True:
                    default = f"{fprint.metadata['name']}.yml"
                    filename = input(f"Output filename [{default}]: ")
                    if filename is None or filename == '':
                        filename = default
                    try:
                        with open(filename, 'w') as f:
                            yaml.dump(fprint.get_output(), f, sort_keys=False)
                        break
                    except IOError:
                        print("Error: unable to open file")
    elif index == 1:
        if dialog("Save all selected fingerprints in one file?"):
            while True:
                default = "multi-fingerprints.yml"
                filename = input(f"Output filename [{default}]: ")
                if filename is None or filename == '':
                    filename = default
                try:
                    with open(filename, 'w') as f:
                        first = True
                        for fprint in fingerprints:
                            if first:
                                first = False
                            else:
                                f.write("---\n")
                            yaml.dump(fprint.get_output(), f, sort_keys=False)
                    break
                except IOError:
                    print("Error: unable to open file")


def save_merged_fingerprint_yaml(fingerprint):
    while True:
        default = f"{fingerprint['metadata']['name']}.yml"
        filename = input(f"Output filename [{default}]: ")
        if filename is None or filename == '':
            filename = default
        try:
            with open(filename, 'w') as f:
                yaml.dump(fingerprint, f, Dumper=MergeDumper, sort_keys=False)
            break
        except IOError:
            print("Error: unable to open file")

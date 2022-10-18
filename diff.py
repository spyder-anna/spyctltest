import sys
import subprocess
import yaml
from merge import merge_fingerprints, DiffDumper
from fingerprints import dialog, catch_interrupt


red = u"\u001b[41;1m \u001b[0m"
green = u"\u001b[42;1m \u001b[0m"
yellow = u"\u001b[43;1m \u001b[0m"
blue = u"\u001b[44;1m \u001b[0m"
magenta = u"\u001b[45;1m \u001b[0m"
cyan = u"\u001b[46;1m \u001b[0m"
color_arr = [red, green, yellow, blue, magenta, cyan]


# pushes all colors to the front
def col_prefix_front(size, colors):
    base = ' ' * (size - len(colors))
    for color in colors:
        base += color_arr[color]
    return base + ' '

# keeps all colors in their own columns
def col_prefix_align(size, colors):
    base = [' '] * size
    for color in colors:
        base[color] = color_arr[color]
    return ''.join(base) + ' '


def num_prefix(size, num, prev_num):
    if num == 0:
        return ' ' * (size + 2)
    s = '|' if num == prev_num else f"{num}."
    return str.rjust(s, size + 1) + ' '


def check_appears(line, def_dash):
    tag_str = "!Appearances:"
    try:
        list_start = line.index(tag_str) + len(tag_str)
        appears = [int(n) for n in line[list_start:].split(',')]
        has_dash = '- ' in line
        return appears, has_dash
    except ValueError:
        return None, def_dash


def get_largest_less_than(tup_list, max_val):
    for elem in tup_list[::-1]:
        if elem[0] <= max_val:
            return elem[1]
    return None


def clear_greater_than(tup_list, max_val):
    for i, elem in enumerate(tup_list):
        if elem[0] > max_val:
            return tup_list[:i]
    return tup_list


def update_max(tup_list, new_tup):
    if tup_list[-1][0] == new_tup[0]:
        tup_list[-1] = new_tup
    else:
        tup_list.append(new_tup)


def format_appearances(string, inputs):
    lines = string.split('\n')
    pre_spaces = len(inputs)
    use_count = pre_spaces > 6
    if use_count:
        pre_spaces = len(str(pre_spaces))
    ret_lines = []
    if not use_count:
        for i, inp in enumerate(inputs):
            indicator = col_prefix_front(pre_spaces, [i])
            ret_lines.append(indicator + inp)
        ret_lines.append(('-' * pre_spaces) + '----')
    indent_appears = [(-1, [])]
    dash_next = False
    prev_count = 0
    for line in lines:
        appears, dash_next = check_appears(line, dash_next)
        indent = len(line) - len(line.lstrip())
        indent_appears = clear_greater_than(indent_appears, indent)
        if appears is not None:
            if dash_next:
                indent += 2
            update_max(indent_appears, (indent, appears))
        else:
            if dash_next:
                line = ' ' * (indent - 2) + '- ' + line[indent:]
                dash_next = False
            appears = get_largest_less_than(indent_appears, indent)
            if use_count:
                prefix = num_prefix(pre_spaces, len(appears), prev_count)
                ret_lines.append(prefix + line)
                prev_count = len(appears)
            else:
                prefix = col_prefix_align(pre_spaces, appears)
                ret_lines.append(prefix + line)
    return '\n'.join(ret_lines) + '\n'


def show_fingerprint_diff(fingerprints):
    merged = merge_fingerprints(fingerprints)
    string = yaml.dump(merged, Dumper=DiffDumper, sort_keys=False)
    def id_str(fprint):
        meta = fprint['metadata']
        return f"{meta['name']}:{meta['muid']}:{meta['root']}"
    string = format_appearances(string, [id_str(fprint) for fprint in fingerprints])
    less_proc = subprocess.Popen(
        ['less', '-R', '-S', '-X', '-K'],
        stdin=subprocess.PIPE, stdout=sys.stdout
    )
    less_proc.communicate(string.encode('utf-8'))
    less_proc.wait()


@catch_interrupt
def save_fingerprint_diff(fingerprints):
    merged = merge_fingerprints(fingerprints)
    show_fingerprint_diff(fingerprints)
    subprocess.call("clear")
    if dialog("Save comparison for viewing?"):
        while(True):
            default = f"compare-fingerprints.txt"
            filename = input(f"Output filename [{default}]: ")
            if filename is None or filename == '':
                filename = default
            try:
                string = yaml.dump(merged, Dumper=DiffDumper, sort_keys=False)
                # feed it a len 7 list to make it use numbers not colors
                string = format_appearances(string, list(range(7)))
                with open(filename, 'w') as f:
                    f.write(string)
                break
            except IOError:
                print("Error: unable to open file")

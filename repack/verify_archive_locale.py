"""Read-only MIKO binary-search reproduction using Windows CompareStringW."""
import argparse
import ctypes
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats import Archive

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Windows CompareStringW is required')
    compare = ctypes.WinDLL('kernel32', use_last_error=True).CompareStringW
    compare.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
    compare.restype = ctypes.c_int
    def cmp(locale, a, b):
        result = compare(locale, 1, a, -1, b, -1)
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result-2
    def find(names, name, locale):
        low, high = 0, len(names)-1
        while low <= high:
            mid = (low+high)//2
            result = cmp(locale, name, names[mid])
            if result == 0:
                return mid
            if result < 0:
                high = mid-1
            else:
                low = mid+1
        return -1
    reports = []
    for path in args.archives:
        raw = path.read_bytes()
        archive = Archive(path, raw)
        if archive.kind != 'MIKO':
            raise ValueError('MIKO archive required: '+path.name)
        names = [e.name for e in archive.entries]
        results = {}
        for label, locale in [('system_default',0x800), ('japanese',0x411), ('korean',0x412)]:
            failed = [i for i,name in enumerate(names) if find(names,name,locale) != i]
            results[label] = {'failed_count':len(failed), 'failed_indices':failed,
                              'adjacent_inversions':sum(cmp(locale,a,b)>0 for a,b in zip(names,names[1:]))}
        reports.append({'file':path.name, 'sha256':hashlib.sha256(raw).hexdigest(), 'entries':len(names), 'checks':results})
    print(json.dumps(reports, indent=2))

if __name__ == '__main__':
    main()

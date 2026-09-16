"""z80/load.py -- readers for the three object formats z80.asm writes.

    segments, entry, name = load_cmd(data)   # a TRS-80 /CMD load module
    segments, entry, name = load_cas(data)   # a Model I SYSTEM tape stream
    segments, entry, name = load_bin(data, org, entry)   # raw bytes

`segments` is [(org, bytes)] in file order, `entry` the transfer address
or None when the file names none, `name` the six-character program name
or ''.  The readers are the input side of the headless runner (and of
whatever loads a program next); they are the mirror of the writers in
z80.asm and tests/test_run.py pins them against each other.  A malformed
file raises LoadError with what was wrong and where.

/CMD records, as LDOS and TRSDOS wrote them: a type byte, a length byte,
the body.  01H is a load block (the length counts the two address bytes
plus the data; a length of 0, 1 or 2 means 256 more, the period
ambiguity, read here as 256 + length), 02H the transfer address, 05H the
module name; 07H (a load-module header) and 1FH (a comment) are skipped.
A SYSTEM tape: a leader of zeros, A5H, then 55H and a six-character
name, then 3CH blocks (count byte, 0 = 256; address low, high; data;
checksum = data + both address bytes, mod 256) and 78H with the entry.
Bytes before A5H are the leader, whatever they hold.
"""


class LoadError(Exception):
    pass


def load_bin(data, org, entry=None):
    if org is None:
        raise LoadError('raw bytes need a load address (--org)')
    return [(org & 0xFFFF, bytes(data))], entry, ''


def load_cmd(data):
    segments, entry, name = [], None, ''
    i, n = 0, len(data)
    while i < n:
        if i + 2 > n:
            raise LoadError('truncated record header at offset %d' % i)
        t, ln = data[i], data[i + 1]
        if t == 0x01 and ln <= 2:
            ln += 256
        body = data[i + 2:i + 2 + ln]
        if len(body) < ln:
            raise LoadError('record %02XH at offset %d wants %d bytes, %d left'
                            % (t, i, ln, len(body)))
        i += 2 + ln
        if t == 0x01:
            a = body[0] | (body[1] << 8)
            segments.append((a, bytes(body[2:])))
        elif t == 0x02:
            if ln < 2:
                raise LoadError('transfer record at offset %d is %d bytes long' % (i, ln))
            entry = body[0] | (body[1] << 8)
            break
        elif t == 0x05:
            name = body.decode('latin-1').rstrip()
        elif t in (0x07, 0x1F, 0x10, 0x1A):
            continue                      # header, comment, DOS-only records: skipped
        else:
            raise LoadError('unknown record type %02XH at offset %d' % (t, i - 2 - ln))
    if not segments:
        raise LoadError('no load blocks')
    return segments, entry, name


def load_cas(data):
    i = data.find(b'\xa5')
    if i < 0:
        raise LoadError('no sync byte (A5H) after the leader')
    i += 1
    if i >= len(data) or data[i] != 0x55:
        raise LoadError('not a SYSTEM tape: 55H does not follow the sync byte')
    name = data[i + 1:i + 7].decode('latin-1').rstrip()
    i += 7
    segments, entry = [], None
    while i < len(data):
        t = data[i]
        if t == 0x3C:
            n = data[i + 1] or 256
            if i + 5 + n > len(data):
                raise LoadError('data block at offset %d runs past the end' % i)
            a = data[i + 2] | (data[i + 3] << 8)
            body = data[i + 4:i + 4 + n]
            want = (sum(body) + data[i + 2] + data[i + 3]) & 0xFF
            if data[i + 4 + n] != want:
                raise LoadError('checksum error in the block at %04XH (offset %d)' % (a, i))
            segments.append((a, bytes(body)))
            i += 5 + n
        elif t == 0x78:
            if i + 3 > len(data):
                raise LoadError('truncated entry record')
            entry = data[i + 1] | (data[i + 2] << 8)
            break
        else:
            raise LoadError('unexpected byte %02XH at offset %d' % (t, i))
    if not segments:
        raise LoadError('no data blocks')
    return segments, entry, name


def load_file(path, org=None, entry=None, fmt=None):
    """Read PATH by its extension (or FMT: bin, cmd, cas).  An .asm file
    is assembled first (z80.asm), so a source file runs directly."""
    import os
    ext = (fmt or os.path.splitext(path)[1].lstrip('.')).lower()
    with open(path, 'rb') as f:
        data = f.read()
    if ext == 'asm':
        from .asm import assemble
        r = assemble(data.decode('latin-1'), org=org, entry=entry)
        if r.errors:
            raise LoadError('\n'.join('%s:%d: %s' % (path, ln, msg) for ln, msg in r.errors))
        return r.segments, r.entry, os.path.splitext(os.path.basename(path))[0]
    if ext == 'cmd':
        segments, e, name = load_cmd(data)
    elif ext == 'cas':
        segments, e, name = load_cas(data)
    else:
        segments, e, name = load_bin(data, org, entry)
    if entry is not None:
        e = entry
    if e is None:
        e = segments[0][0]
    return segments, e, name

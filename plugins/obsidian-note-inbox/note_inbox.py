#!/usr/bin/env python3
"""Write one UTF-8 Markdown note to an explicitly chosen directory, without overwrites."""

import argparse
import errno
import os
import secrets
import stat
import sys

MAX_NOTE_BYTES = 256 * 1024
MAX_FILENAME_BYTES = 240


class InvalidInput(Exception):
    pass


class Conflict(Exception):
    pass


def validate_filename(name):
    if (not name or name.startswith('.') or name != name.strip()
            or any(char in '/\\:*?"<>|#^' for char in name)
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or not name.lower().endswith('.md')
            or len(name.encode('utf-8')) > MAX_FILENAME_BYTES):
        raise InvalidInput


def validate_content(content):
    if not content or len(content) > MAX_NOTE_BYTES or b'\x00' in content:
        raise InvalidInput
    try:
        decoded = content.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise InvalidInput from exc
    if not decoded.strip():
        raise InvalidInput


def open_directory(path):
    """Open every component without following symlinks; return a directory fd."""
    if not path.startswith('/') or '\x00' in path:
        raise InvalidInput
    components = path.split('/')
    if any(part in ('.', '..') for part in components):
        raise InvalidInput
    if not all(hasattr(os, key) for key in ('O_DIRECTORY', 'O_NOFOLLOW')):
        raise OSError('safe directory opening is unavailable')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        for part in components:
            if not part:
                continue
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def matches_existing(directory_fd, name, content):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EISDIR):
            raise Conflict from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(content):
            return False
        chunks = []
        remaining = MAX_NOTE_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks) == content
    finally:
        os.close(fd)


def write_note(directory, name, content):
    validate_filename(name)
    validate_content(content)
    directory_fd = open_directory(directory)
    temporary_name = None
    try:
        # The hidden temporary Markdown file lives on the destination filesystem.
        # link() publishes complete bytes atomically and fails if the name exists.
        for _ in range(10):
            candidate = '.note-inbox-' + secrets.token_hex(16) + '.md'
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError('could not create temporary file')
        try:
            view = memoryview(content)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError('short write')
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(temporary_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    follow_symlinks=False)
        except FileExistsError:
            if matches_existing(directory_fd, name, content):
                return 'duplicate'
            raise Conflict
        return 'created'
    finally:
        try:
            if temporary_name is not None:
                os.unlink(temporary_name, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Store a new Markdown note from standard input.')
    parser.add_argument('--inbox', required=True, help='Explicit absolute destination directory')
    parser.add_argument('--name', required=True, help='Markdown filename, without directories')
    args = parser.parse_args(argv)
    try:
        content = sys.stdin.buffer.read(MAX_NOTE_BYTES + 1)
        result = write_note(args.inbox, args.name, content)
    except (InvalidInput, UnicodeError):
        print('invalid input', file=sys.stderr)
        return 2
    except Conflict:
        print('destination conflict', file=sys.stderr)
        return 3
    except OSError:
        print('storage failed', file=sys.stderr)
        return 4
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

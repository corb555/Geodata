#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#  Copyright (c) 2019.       Mike Herbert
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA

"""        Read a file and call a handler for each line. Update progress bar if present.  """
import logging
import os


class FileReader:

    def __init__(self, directory: str, filename: str, update_progress, prefix=''):
        """
        Read a file and call a handler for each line.  Update progress bar if present
        #Args:
            directory:
            filename:
            progress_bar: Progress Bar or None
        """
        self.logger = logging.getLogger(__name__)
        self.directory: str = directory
        self.update_progress = update_progress
        self.fname: str = filename
        self.cache_changed = False
        self.count = 0
        self.prefix = prefix

    def read(self) -> bool:
        """
        Read a file and call a handler for each line.  Update progress bar
        :return: Error
        """
        line_num = 0
        file_pos = 0

        path = os.path.join(self.directory, self.fname)
        self.logger.info(f"Reading file {path}")
        if os.path.exists(path):
            fsize = os.path.getsize(path)
            with open(path, 'r', newline="", encoding='utf-8', errors='replace') as file:
                for row in file:
                    line_num += 1
                    file_pos += len(row)
                    self.handle_line(line_num, row)
                    if line_num % 80000 == 1:
                        # Periodically update progress
                        prog = file_pos * 100 / fsize
                        self.progress(f"{self.prefix} Loading {self.fname} {prog:.0f}%", prog)

            self.cache_changed = True
            self.progress("", 100)
            self.logger.info(f'Added {self.count} items')
            return False
        else:
            self.logger.error(f'Unable to open {path}')
            return True

    def cancel(self):
        # User requested cancel of file read
        pass

    def handle_line(self, line_num: int, row: str) -> int:
        # Handle the line we read
        pass

    def progress(self, msg, val):
        """ Update progress bar if there is one """
        if self.update_progress is not None:
            self.update_progress(val, msg)

        # If we're past 80% log item as info, otherwise log as debug
        if val > 90 or val < 10 or (val > 40 and val < 50):
            self.logger.info(f'{val:.1f}%  {msg}')
        else:
            self.logger.debug(f'{val:.1f}%  {msg}')


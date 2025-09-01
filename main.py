#!/usr/bin/env python3.13
                                     
#  _ __   __ _ _ __   __ _            
# | '_ \ / _` | '_ \ / _` |           
# | |_) | (_| | |_) | (_| |           
# | .__/ \__,_| .__/ \__,_|____ _____ 
# | |   (_)   | |        |_   _|_   _|
# |_|__  _ ___|_|____ _    | |   | |  
# | '_ \| |_  /_  / _` |   | |   | |  
# | |_) | |/ / / / (_| |  _| |_ _| |_ 
# | .__/|_/___/___\__,_| |_____|_____| 🍕
# | |                           by esi ✦  
# |_|                                 

import sqlite3

from termcolor import cprint, colored
from colorama import just_fix_windows_console as enable_windows_ansi_interpretation

enable_windows_ansi_interpretation()

def create_database():
    cx = sqlite3.connect("papa_pizza.db")
    cu = cx.cursor()
    cx.autocommit = True

    pass

    # cx.commit()
    cx.close()

def main():
    create_database()

if __name__ == "__main__":
    main()


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
import signal
import sys
import atexit

from typing import Callable
import inspect

from termcolor import cprint, colored
from colorama import just_fix_windows_console as enable_windows_ansi_interpretation

# fix windows terminal misinterpreting ANSI escape sequences
enable_windows_ansi_interpretation()

class DatabaseHandler:
    cx: sqlite3.Connection | None = None
    cu: sqlite3.Cursor | None = None

    @staticmethod
    def connect():
        try:
            cprint("connecting to papa-pizza database...", "yellow")
            DatabaseHandler.cx = sqlite3.connect("papa_pizza.db")
            cprint("connected.", "green")
        except sqlite3.Error as e:
            cprint(f"database connection failure: {str(e)}", "red")
            return

        DatabaseHandler.cu = DatabaseHandler.cx.cursor()
        DatabaseHandler.cx.autocommit = True

    @staticmethod
    def close():
        cprint("closing database connection...", "magenta")
        
        if DatabaseHandler.cx:
            DatabaseHandler.cx.close()
            cprint("database connection closed!", "green")

def parse_boolean_input(prompt: str, handle_invalid: bool = False) -> bool:
    """Parse 'y/n' input, returning True for yes. Invalid only retried if handle_invalid=True."""
    if prompt.lower() in ["y", "yes"]:
        return True
    elif prompt.lower() in ["n", "no"] or not handle_invalid:
        return False
    else:
        cprint("invalid input, please try again.", "red")
        return False
    
class Command:
    """Bind a CLI command name to a function and its description."""
    def __init__(self, name: str, function: Callable, description: str):
        self.name = name
        self.__function__ = function
        self.description = description

    def execute(self, tokens: list[str], required_count=None):
        """Validate argument count then invoke the bound function."""
        signature = inspect.signature(self.__function__)
        params = list(signature.parameters.values())

        #
        required_param_count = sum(
            param.default == inspect.Parameter.empty and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
            for param in params
        )

        # Validate token count
        if not required_param_count <= len(tokens) <= len(params):
            cprint(f"invalid number of arguments for command '{self.name}' — (expected {required_count}-{len(params)}, got {len(tokens)})", "red")
            return None

        return self.__function__(*tokens)

class CommandParser:
    """Parse user input, map to commands, and run them in a REPL."""
    def __init__(self):
        # Register basic commands
        self.commands = [
            Command("help", self.show_help, "Display this help message."),
            Command("h", self.show_help, "Alias for 'help'."),
            Command("quit", Application.quit, "Exit the program."),
            Command("exit", lambda: cprint("use quit to exit", "yellow"), "Alias for 'quit'."),
        ]

    def parse_and_execute(self, input_str):
        """Match the input string to a registered command and execute."""
        tokens = input_str.strip().split()
        
        for command in self.commands:
            name_parts = command.name.split()
            # if the command name matches the input, omit the matching indexes
            if tokens[:len(name_parts)] == name_parts:
                args = tokens[len(name_parts):]
                return command.execute(args)
        
        cprint("unknown command. type 'help'.", "red")
        return None

    def show_help(self):
        """Display help with all available command names and descriptions."""
        cprint("available commands:", "green", attrs=["bold"])
        for cmd in self.commands:
            signature = inspect.signature(cmd.__function__)

            # format params
            params = " ".join(
                f"<{param} {value.default if value.default is not None else '(optional)'}>"
                for param, value in signature.parameters.items()
            )

            # concatenate command name and params
            cmd_with_params = f"{colored(cmd.name, 'blue')} {colored(params, 'cyan')}"

            print(f"{cmd_with_params.ljust(max(len(cmd.name) for cmd in self.commands) + 50)}  {cmd.description}")

    # User input menu
    def start_repl(self):
        """Begin the interactive prompt loop until quit."""
        while True:
            user_input = input(colored("\n> ", "blue")).strip()
            if user_input:
                self.parse_and_execute(user_input)

class Application:
    """Wire together CLI commands with the OrderManager and start the REPL."""
    def __init__(self, *args):
        parser = CommandParser()
        
        parser.commands.append(Command("customers show", lambda: cprint("not implemented yet you bum", "red"), "Show the menu"))
        
        
        cprint("""
welcome to papa-pizza, the sequel!!! 🍕,
your local pizza store's customer database!
           
by vapidinfinity, aka esi
    """, "green", attrs=["bold"])

        print("""this is a simple command line interface for managing customers in papa-pizza, the world-renowned pseudo pizza store
              
for more information, type 'help' or 'h' at any time.
to exit the program, type 'quit' or 'exit'.""")

        # if args are passed directly into the exec, parse and execute them
        if args:
            parser.parse_and_execute(" ".join(args))

        parser.start_repl()
    
    @staticmethod
    def _quit():
        DatabaseHandler.close()
        cprint("okay, see ya!", "green")
        sys.exit(0)
        
    @staticmethod
    def quit():
        """Prompt for confirmation and exit the application on yes."""
        prompt = input(colored("are you sure you want to quit? (y/N): ", "yellow"))
        if parse_boolean_input(prompt, handle_invalid=False):
            Application._quit()
        else:
            cprint("okay, continuing...", "green")
            return

# main function to run the program
def main():
    """Entry point: instantiate Application with optional CLI args."""
    args = sys.argv[1:]
    Application(*args)

class SignalHandler:
    """Handle system SIGINT (Ctrl+C) to remind user to use 'quit'."""
    # signal handler to handle ctrl+c
    @staticmethod
    def sigint(_, __):
        """Custom SIGINT handler printing a warning then exiting."""
        cprint("\n" + "next time, use quit!", "yellow")
        Application._quit()

# register signal handler for (ctrl+c) SIGINT
signal.signal(signal.SIGINT, lambda _, __: Application._quit())

if __name__ == "__main__":
    main()


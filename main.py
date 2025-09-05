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

# note from esi:
# i used ai to tidy the code because it was a bloody mess
# --sql is used for syntax highlighting inline sql queries

import sqlite3
import signal
import sys

from typing import Callable
from abc import ABC, abstractmethod
from enum import Enum
import inspect

from termcolor import cprint, colored
from colorama import just_fix_windows_console as enable_windows_ansi_interpretation

# fix windows terminal misinterpreting ANSI escape sequences
enable_windows_ansi_interpretation()

class DatabaseManager:
    def __init__(self):
        # initialise and configure db connection
        self.conn = sqlite3.connect("papa-pizza.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.autocommit = True
        self.conn.execute("--sql\nPRAGMA foreign_keys=ON;")
        
        self.__create_schema__()
        self._seed_menu()
        self._seed_default_user()

    def __create_schema__(self):
        self.conn.executescript(
            """--sql
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL, -- should be seeded but cmon now it's a school project
                privilege_level INT NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                service_type INTEGER NOT NULL,
                has_loyalty_card INTEGER NOT NULL,
                is_discounted INTEGER NOT NULL DEFAULT 0,
                paid INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES accounts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY(menu_item_id) REFERENCES menu(id)
            );
            """
        )

    def _seed_menu(self):
        pizzas = [
            ("Pepperoni", 21.00),
            ("Chicken Supreme", 23.50),
            ("BBQ Meatlovers", 25.50),
            ("Veg Supreme", 22.50),
            ("Hawaiian", 19.00),
            ("Margherita", 18.50),
        ]

        # insert menu items if not already present (name-dependent)
        self.conn.executemany(
            """--sql
            INSERT OR IGNORE INTO menu(name, price) VALUES(?, ?);
            """, pizzas
        )
    
    def _seed_default_user(self):
        self.conn.execute(
            """--sql
            INSERT OR IGNORE INTO accounts(username, password, privilege_level)
            VALUES (?, ?, ?)
            """, ("admin", "admin", AccountManager.PrivilegeLevel.ADMIN.value)
        )

class AccountManager:
    """Manage user accounts, including login and privilege checks."""
    def __init__(self, db: DatabaseManager):
        self.db = db
        self._current_user_id: int | None = None
        self.current_privilege: int = 0

    class PrivilegeLevel(Enum):
        """Enumeration of privilege levels for user accounts."""
        USER = 0
        ADMIN = 1

    def _login(self, username: str, password: str) -> bool:
        """Low-level authenticate (no prompting)."""
        user = self.db.conn.execute(
            "SELECT id, privilege_level FROM accounts WHERE username=? AND password=?;",
            (username, password)
        ).fetchone()
        if not user:
            return False
        self.current_user_id = user["id"]
        self.current_privilege = user["privilege_level"]
        level_name = AccountManager.PrivilegeLevel(user["privilege_level"]).name.lower()
        prefix = f"{level_name}: " if level_name != "user" else ""
        cprint(f"logged in as {prefix}{colored(username, 'yellow', attrs=['bold'])}", "green")
        return True

    def login(self, username: str | None = None, password: str | None = None):
        """Interactive login (prompts until success if creds not provided)."""
        if username is not None and password is not None:
            if not self._login(username, password):
                cprint("invalid username or password", "red")
            return
        # prompt loop
        while True:
            user = input(colored("username: ", "magenta")).strip()
            pwd = input(colored("password: ", "magenta")).strip()
            if self._login(user, pwd):
                break
            cprint("invalid username or password", "red")

    def user_exists(self, username: str) -> bool:
        """Check if a user with the given username exists."""
        user = self.db.conn.execute(
            "SELECT id FROM accounts WHERE username=?;",
            (username,)
        ).fetchone()
        
        return user is not None
    
    def logout(self):
        """Log out the current user."""
        if self.current_user_id is not None:
            cprint(f"logged out user with id #{self.current_user_id} successfully", "green")
            self.current_user_id = None
            self.current_privilege = 0
        else:
            cprint("no user currently logged in", "red")

    def is_admin(self):
        return self.current_privilege == AccountManager.PrivilegeLevel.ADMIN.value

    @property
    def current_user_id(self):
        return self._current_user_id

# establish a base class for order items
class OrderItem(ABC):
    """Abstract base class for items that can be ordered."""
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def price(self) -> float:
        pass

# pizza implementation uses `OrderItem` as its base class 👍🏾👍🏾👍🏾👍🏾
class Pizza(OrderItem):
    """Concrete OrderItem representing a pizza with a name and a price."""
    def __init__(self, name: str, price: float):
        self._name = name
        self._price = price
        
    @property
    def name(self) -> str:
        return self._name

    @property
    def price(self) -> float:
        return self._price

class ServiceType(Enum):
    """Enumeration of service types: pickup or delivery."""
    PICKUP = 0
    DELIVERY = 1

menu: list[OrderItem] = []  # will be loaded dynamically because i am literally einstein

def reload_menu(order_manager):
    """Reload global menu from any object exposing fetch_menu()."""
    global menu
    menu = [Pizza(r["name"], r["price"]) for r in order_manager.fetch_menu()]

class Order:
    """Order view model using DB autoincrement id."""
    def __init__(self, order_id: int, items: list[OrderItem], service_type: ServiceType, has_loyalty_card: bool, is_discounted=False, paid=False):
        self.id = order_id
        self.items = items
        self.service_type = service_type
        self.has_loyalty_card = has_loyalty_card
        self.is_discounted = is_discounted
        self.paid = paid

    # Calculate the cost of the order based on menu prices
    @property
    def raw_cost(self):
        """Return sum of item prices before discounts, fees, or taxes."""
        return sum(item.price for item in self.items)
    
    # Calculate total cost, apply discounts and delivery charges
    @property
    def total_cost(self):
        """Compute total cost including discounts, delivery fee, and GST"""
        base = self.raw_cost
        discount_eligible = base > 100 or self.has_loyalty_card
        if discount_eligible:
            # mark once; calculation always from base so no compounding
            if not self.is_discounted:
                self.is_discounted = True
            cost = base * 0.95
        else:
            cost = base

        if self.service_type is ServiceType.DELIVERY:
            cost += 8.00
        elif self.service_type is not ServiceType.PICKUP:
            raise ValueError("Invalid service type!")

        return cost * 1.1 # add 10% GST
    
class OrderManager:
    """Manage creation, modification, processing, and listing of multiple orders."""
    def __init__(self, db: DatabaseManager, account_manager: AccountManager):
        self.db = db
        self.account_manager = account_manager
        self.orders: list[Order] = []
        self.current_order_id: int | None = None
        reload_menu(self)
        self._update_orders()

    def _update_orders(self):
        self.orders.clear()
        for row in self.fetch_orders():
            items_rows = self.fetch_items_for_order(row["id"])
            items = [Pizza(r["name"], r["price"]) for r in items_rows]
            self.orders.append(
                Order(
                    order_id=row["id"],
                    items=items,
                    service_type=ServiceType(row["service_type"]),
                    has_loyalty_card=bool(row["has_loyalty_card"]),
                    is_discounted=bool(row["is_discounted"]),
                    paid=bool(row["paid"]),
                )
            )
    
    def fetch_menu(self):
        return self.db.conn.execute("SELECT name, price FROM menu ORDER BY id;").fetchall()

    def get_menu_item(self, name: str):
        return self.db.conn.execute(
            "SELECT id, name, price FROM menu WHERE lower(name)=lower(?);",
            (name,),
        ).fetchone()

    def insert_order(self, service_type: int, has_loyalty: bool) -> int:
        # Attach order to current user if signed in
        customer_id = self.account_manager.current_user_id
        cur = self.db.conn.execute(
            "INSERT INTO orders(customer_id, service_type, has_loyalty_card) VALUES(?,?,?);",
            (customer_id, service_type, int(has_loyalty)),
        )
        return cur.lastrowid

    def delete_order(self, order_id: int):
        self.db.conn.execute("DELETE FROM orders WHERE id=?;", (order_id,))

    def fetch_orders(self):
        """Return orders visible to current user (all if admin, own only otherwise)."""
        if self.account_manager.is_admin():
            return self.db.conn.execute(
                "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders ORDER BY id;"
            ).fetchall()
        uid = self.account_manager.current_user_id
        return self.db.conn.execute(
            "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE customer_id=? ORDER BY id;",
            (uid,),
        ).fetchall()

    def fetch_order_by_id(self, order_id: int):
        """Fetch single order row (includes customer_id for ownership checks)."""
        return self.db.conn.execute(
            "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE id=?;",
            (order_id,),
        ).fetchone()

    def _db_add_order_item(self, order_id: int, menu_name: str):
        """Insert a single menu item row for an order."""
        menu_row = self.get_menu_item(menu_name)
        if not (self.fetch_order_by_id(order_id) and menu_row):
            return False
        self.db.conn.execute(
            "INSERT INTO order_items(order_id, menu_item_id) VALUES(?, ?);",
            (order_id, menu_row["id"]),
        )
        return True

    def _db_remove_order_item(self, order_id: int, menu_name: str):
        """Remove one occurrence of a menu item from an order."""
        menu_row = self.get_menu_item(menu_name)
        if not (self.fetch_order_by_id(order_id) and menu_row):
            return False
        self.db.conn.execute(
            """--sql
            DELETE FROM order_items
            WHERE rowid IN (
                SELECT order_items.rowid FROM order_items
                WHERE order_items.order_id=? AND order_items.menu_item_id=?
                LIMIT 1
            );
            """,
            (order_id, menu_row["id"]),
        )
        return True

    def fetch_items_for_order(self, order_id: int):
        return self.db.conn.execute(
            """--sql
            SELECT menu.name, menu.price
            FROM order_items
            JOIN menu ON menu.id = order_items.menu_item_id
            WHERE order_items.order_id=?
            ORDER BY order_items.id;
            """,
            (order_id,),
        ).fetchall()

    def update_paid_and_discount(self, order_id: int, paid: bool, discounted: bool):
        self.db.conn.execute(
            "UPDATE orders SET paid=?, is_discounted=? WHERE id=?;",
            (int(paid), int(discounted), order_id),
        )

    def fetch_paid_orders(self):
        """Return paid orders in scope (all if admin, own only otherwise)."""
        if self.account_manager.is_admin():
            return self.db.conn.execute(
                "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE paid=1 ORDER BY id;"
            ).fetchall()
        uid = self.account_manager.current_user_id
        return self.db.conn.execute(
            "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE paid=1 AND customer_id=? ORDER BY id;",
            (uid,),
        ).fetchall()

    def print_order(self, order: Order):
        cprint(f"order #{order.id} ({order.service_type.name.lower()}):", "green")
        print("\t" + f"items: {', '.join(i.name for i in order.items) or 'none'}")
        print("\t" + f"service type: {order.service_type.name}")
        print("\t" + f"total cost: ${order.total_cost:.2f}")
        print("\t" + f"paid: {'yes' if order.paid else 'no'}")

    def list_orders(self):
        """List all orders or report none exist."""
        if not self.orders:
            cprint("no orders found :(", "red")
            return

        for o in self.orders:
            self.print_order(o)

    def _get_order_by_id(self, order_id: int | None) -> Order | None:
        return next((o for o in self.orders if o.id == order_id), None)

    # Add an order to the system
    def create_order(self, type: str | None = None):
        """Interactively prompt to create a new order with service type and loyalty flag."""
        # (auth already enforced globally; per-method check removed)
        # prompt service type
        if type is None:
            type = input("Order type? (pickup/delivery): ").strip().lower()

        try:
            service_type = ServiceType[type.upper()]
        except:
            cprint("invalid service type!", "red")
            return
        
        # prompt loyalty card status
        prompt = input("does customer have a loyalty card? (y/N): ").strip().lower()
        has_loyalty = parse_boolean_input(prompt, handle_invalid=False)

        new_id = self.insert_order(service_type.value, has_loyalty)
        self._update_orders()
        cprint(f"order #{new_id} created successfully!", "green")
        self.current_order_id = new_id

    # Remove an order from the system
    def remove_order(self):
        """Interactively remove an order by its list index."""
        self.list_orders()
        if not self.orders:
            return
        prompt = input("enter order id to remove: ").strip()
        if not prompt.isdigit():
            cprint("invalid order id", "red")
            return
        order_id = int(prompt)
        order = self._get_order_by_id(order_id)
        if not order:
            cprint("order not found", "red")
            return
        
        # only allow removing own orders (unless admin)
        if not self.account_manager.is_admin():
            db_row = self.fetch_order_by_id(order_id)
            if db_row and db_row["customer_id"] != self.account_manager.current_user_id:  # fixed .get misuse
                cprint("you can only remove your own orders.", "red")
                return
            
        self.delete_order(order_id)
        if self.current_order_id == order_id:
            self.current_order_id = None
        self._update_orders()
        cprint(f"order #{order_id} removed successfully!", "green")

    # switch order focus    
    def switch_order(self):
        """Interactively switch the current focus to an existing order."""
        self.list_orders()
        if not self.orders:
            return
        prompt = input("enter order id to switch to: ").strip()
        if not prompt.isdigit():
            cprint("invalid order id", "red")
            return
        order_id = int(prompt)
        if not self._get_order_by_id(order_id):
            cprint("order not found", "red")
            return
        if self.current_order_id == order_id:
            cprint("this is already your current order!", "yellow")
            return
        self.current_order_id = order_id
        cprint(f"switched to order #{order_id}", "green")

    def _check_current_order(self):
        """Ensure there's a valid, unpaid current order or prompt next steps."""
        order = self._get_order_by_id(self.current_order_id)
        if order is None:
            cprint("no current order selected.", "red")
            if self.orders:
                prompt = input("would you like to select an order? (y/N): ")
                if parse_boolean_input(prompt, handle_invalid=True):
                    self.switch_order()
                    return
            else:
                prompt = input("would you like to create an order? (y/N): ")
                if parse_boolean_input(prompt, handle_invalid=True):
                    self.create_order()
                    return
        else:
            if order.paid:
                cprint("this order has already been paid for.", "red")
                prompt = input("would you like to switch to a different order? (y/N): ")
                if parse_boolean_input(prompt, handle_invalid=True):
                    self.switch_order()
                    return
                
    
    def add_order_item(self, item: str | None = None, quantity: str | None = "1"):
        """Add a menu item in given quantity to the current order."""
        # Prompt for item if not provided
        if item is None:
            item = input("enter the name of the menu item you'd like to add: ").strip().lower()

        item = next((menu_item for menu_item in menu if menu_item.name.lower() == item), None)
        
        if item is None:
            cprint("invalid menu item", "red")
            return

        # Validate quantity
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except:
            prompt = input("Enter a valid quantity (1 or more): ")
            if not prompt.isdigit() or int(prompt) < 1:
                cprint("invalid quantity", "red")
                return
            quantity = int(prompt)

        # check for maximum quantity
        if quantity > 10:
            cprint("maximum quantity is 10 at a time. try adding items again to add more.", "red")
            return

        for _ in range(quantity):
            self._add_order_item(item)

    def _add_order_item(self, item: OrderItem):
        """Helper to append a single OrderItem to the current order."""
        self._check_current_order()
        order = self._get_order_by_id(self.current_order_id)
        if order is None:
            return
        if not self._db_add_order_item(order.id, item.name):
            cprint("failed to add item.", "red")
            return
        order.items.append(item)
        cprint(f"added {item.name} to order #{order.id}", "green")


    def remove_order_item(self):
        """Interactively remove a given quantity of a menu item from the current order."""
        prompt = input("which menu item would you like to remove?: ")
        prompt = prompt.strip().lower()

        item = next((item for item in menu if item.name.lower() == prompt), None)
        if item is None:
            cprint("invalid menu item", "red")
            return
        
        prompt = input("how many of this item would you like to remove? ")
        if not prompt.isdigit() or int(prompt) < 1:
            cprint("invalid quantity", "red")
            return
        quantity = int(prompt)

        for _ in range(quantity):
            self._remove_order_item(item)

    def _remove_order_item(self, item: OrderItem):
        """Helper to remove a single OrderItem from the current order."""
        self._check_current_order()
        order = self._get_order_by_id(self.current_order_id)
        if order is None:
            return
        if self._db_remove_order_item(order.id, item.name) and item in order.items:
            # remove first occurrence in in-memory list to stay in sync with DB
            for i, existing in enumerate(order.items):
                if existing.name == item.name:
                    del order.items[i]
                    break
            cprint(f"removed {item.name} from order #{order.id}", "green")
        else:
            cprint(f"{item.name} not in current order.", "red")


    # Process orders
    def process_order(self):
        """Process payment for the current order, apply extras, and record it in daily sales."""
        self._check_current_order()

        order = self._get_order_by_id(self.current_order_id)
        if order is None:
            return

        if order.paid:
            cprint("order already paid.", "red")
            return

        extras = []
        # constants so i can be lazy and hardcode it
        preview_total = order.total_cost  # sets order.is_discounted if applicable
        if order.is_discounted:
            extras.append("a 10% discount")
        if order.service_type is ServiceType.DELIVERY:
            extras.append("$8.00 delivery")

        extras.append("10% GST")

        # smoothly concatenate the extras!
        extras_str = f", including {' and '.join(extras)}" if extras else ""
        print(f"the total for order #{order.id} is ${preview_total:.2f}{extras_str}.")
        prompt = input("would you like to pay now? (y/N): ")
        if parse_boolean_input(prompt, handle_invalid=True):
            order.paid = True
            # persist final flags
            self.update_paid_and_discount(order.id, True, order.is_discounted)
            cprint(f"order #{order.id} paid successfully!", "green")
        else:
            cprint("payment cancelled", "yellow")

    # Generate daily sales summary
    def generate_daily_sales_summary(self):
        """Print each paid order’s total and the grand total sales for the day."""
        rows = self.fetch_paid_orders()
        if not rows:
            cprint("no sales to summarise :(", "red")
            return
        total_sales = 0.0
        for row in rows:
            items_rows = self.fetch_items_for_order(row["id"])
            items = [Pizza(r["name"], r["price"]) for r in items_rows]
            temp = Order(
                order_id=row["id"],
                items=items,
                service_type=ServiceType(row["service_type"]),
                has_loyalty_card=bool(row["has_loyalty_card"]),
                is_discounted=bool(row["is_discounted"]),
                paid=True,
            )
            order_total = temp.total_cost
            
            # indicate owner when admin viewing all
            owner_suffix = " "+f"(user #{row['customer_id']})" if self.account_manager.is_admin() else ""
            print(f"order #{temp.id}{owner_suffix}: {colored(f'${order_total:.2f}', 'green')}")
            total_sales += order_total
            
        cprint(f"total sales for today: ${total_sales:.2f}", "green")
        cprint("thank you for using papa-pizza!", "green")

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
        required_param_count = sum(
            p.default == inspect.Parameter.empty and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY
            ) for p in params
        )
        if not required_param_count <= len(tokens) <= len(params):
            cprint(
                f"invalid number of arguments for command '{self.name}' — (expected {required_param_count}-{len(params)}, got {len(tokens)})",
                "red"
            )
            return None
        return self.__function__(*tokens)

class CommandParser:
    """Parse user input, map to commands, and run them in a REPL."""
    def __init__(self, account_manager=None):
        # Register basic commands
        self.account_manager = account_manager
        
        self.commands = [
            Command("help", self.show_help, "Display this help message."),
            Command("h", self.show_help, "Alias for 'help'."),
            Command("quit", self.quit, "Exit the program."),
            Command("exit", lambda: cprint("use quit to exit", "yellow"), "Alias for 'quit'."),
        ]

    def parse_and_execute(self, input_str):
        """Match the input string to a registered command and execute."""
        tokens = input_str.strip().split()
        for command in self.commands:
            name_parts = command.name.split()
            if tokens[:len(name_parts)] == name_parts:
                if self.account_manager and self.account_manager.current_user_id is None:
                    cprint("please sign in first.", "red")
                    return None
                args = tokens[len(name_parts):]
                return command.execute(args)
        
        cprint("unknown command. type 'help'.", "red")
        return None

    def show_help(self):
        """Display help with all available command names and descriptions."""
        cprint("available commands:", "green", attrs=["bold"])
        for cmd in self.commands:
            # Only show admin commands if user is admin
            if "[admin]" in cmd.description and (not self.account_manager or not self.account_manager.is_admin()):
                continue
            signature = inspect.signature(cmd.__function__)

            # format params
            params = " ".join(
                f"<{param} {value.default if value.default is not None else '(optional)'}>"
                for param, value in signature.parameters.items()
            )

            # concatenate command name and params
            cmd_with_params = f"{colored(cmd.name, 'blue')} {colored(params, 'cyan')}"

            print(f"{cmd_with_params.ljust(max(len(cmd.name) for cmd in self.commands) + 50)}  {cmd.description}")

    # Exit the program
    @staticmethod
    def quit():
        """Prompt for confirmation and exit the application on yes."""
        prompt = input(colored("are you sure you want to quit? (y/N): ", "yellow"))
        if parse_boolean_input(prompt, handle_invalid=False):
            cprint("okay, see ya!", "green")
            sys.exit(0)
        else:
            cprint("okay, continuing...", "green")
            return

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
        self.db = DatabaseManager()
        self.account_manager = AccountManager(self.db)
        self.order_manager = OrderManager(self.db, self.account_manager)
        parser = CommandParser(self.account_manager)
        
        # register commands
        parser.commands.append(Command("menu", self.show_menu, "Show the menu"))

        parser.commands.append(Command("order create", self.order_manager.create_order, "Add an order"))
        parser.commands.append(Command("order remove", self.order_manager.remove_order, "Remove an order (by id)"))
        parser.commands.append(Command("order list", self.order_manager.list_orders, "List all orders"))
        parser.commands.append(Command("order process", self.order_manager.process_order, "Process an order"))
        parser.commands.append(Command("order switch", self.order_manager.switch_order, "Switch current order (by id)"))

        parser.commands.append(Command("order item add", self.order_manager.add_order_item, "Add an item to the current order"))
        parser.commands.append(Command("order item remove", self.order_manager.remove_order_item, "Remove an item from the current order"))

        parser.commands.append(Command("order summary", self.order_manager.generate_daily_sales_summary, "Generate daily sales summary"))

        cprint("""
welcome to papa-pizza, the sequel!!! 🍕,
your local pizza store's customer database!
           
by vapidinfinity, aka esi
    """, "green", attrs=["bold"])

        print("""this is a simple command line interface for managing customers in papa-pizza, the world-renowned pseudo pizza store
              
for more information, type 'help' or 'h' at any time.
to exit the program, type 'quit' or 'exit'.""")
        
        self.account_manager.login()

        if args:
            parser.parse_and_execute(" ".join(args))
        
        parser.start_repl()

    @staticmethod
    def show_menu():
        """Print Papa Pizza’s menu of available items."""
        cprint("papa-pizza's famous menu", None, attrs=["bold"])

        current_item = None
        for item in menu:
            if type(item) is not type(current_item):
                current_item = item
                cprint(f"\n{type(item).__name__}:", "green", attrs=["bold"])
                
            cprint(f"{item.name}: ${item.price:.2f}", "green")
    
    
            
# Main function to run the program
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
        sys.exit(0)

# register signal handler for (ctrl+c) SIGINT
signal.signal(signal.SIGINT, SignalHandler.sigint)

if __name__ == "__main__":
    main()
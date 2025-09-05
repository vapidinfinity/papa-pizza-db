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
# i used ai to tidy the code TWICE because it was a bloody mess
# --sql is used for syntax highlighting inline sql queries

import sqlite3
import signal
import sys
import atexit
import inspect
from dataclasses import dataclass
from typing import Callable, Sequence
from abc import ABC, abstractmethod
from enum import Enum

from termcolor import cprint, colored
from colorama import just_fix_windows_console as enable_windows_ansi_interpretation

# fix windows terminal misinterpreting ansi escape sequences
enable_windows_ansi_interpretation()

# constants
GST_RATE = 0.10
DISCOUNT_RATE = 0.05
DELIVERY_FEE = 8.00
DISCOUNT_THRESHOLD = 100.0
MAX_BATCH_ITEM_ADD = 10

# helpers
def safe_int(value: str, minimum: int | None = None):
    """return int value or none if invalid / below minimum"""
    try:
        v = int(value)
        if minimum is not None and v < minimum:
            return None
        return v
    except ValueError:
        return None

def color_money(amount: float) -> str:
    """format amount as green money string"""
    return colored(f"${amount:.2f}", "green")

def parse_boolean_input(prompt: str, handle_invalid: bool = False) -> bool:
    """parse y/n style input; optionally warn on invalid"""
    p = prompt.lower().strip()
    if p in ("y", "yes"):
        return True
    if p in ("n", "no"):
        return False
    if handle_invalid:
        cprint("invalid input, please try again.", "red")
    return False

# database layer
class DatabaseManager:
    """manage sqlite connection and schema (yes still flat + simple)"""
    def __init__(self):
        self.conn = sqlite3.connect("papa-pizza.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.autocommit = True
        self.conn.execute("--sql\nPRAGMA foreign_keys=ON;")
        self._create_schema()
        self._seed_menu()
        self._seed_default_user()

    def _create_schema(self):
        """create tables / triggers / view if missing"""
        self.conn.executescript(
            """--sql
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password TEXT NOT NULL, -- should be hashed but cmon now it's a school project
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
            CREATE TRIGGER IF NOT EXISTS trg_menu_price_insert
            BEFORE INSERT ON menu
            WHEN NEW.price <= 0
            BEGIN
                SELECT RAISE(ABORT, 'price must be positive');
            END;
            CREATE TRIGGER IF NOT EXISTS trg_menu_price_update
            BEFORE UPDATE ON menu
            WHEN NEW.price <= 0
            BEGIN
                SELECT RAISE(ABORT, 'price must be positive');
            END;
            CREATE VIEW IF NOT EXISTS order_totals AS
            SELECT
                o.id AS order_id,
                o.customer_id,
                o.service_type,
                o.has_loyalty_card,
                o.is_discounted,
                o.paid,
                o.created_at,
                COALESCE(SUM(m.price),0) AS base_total,
                CASE WHEN COALESCE(SUM(m.price),0) > 100 OR o.has_loyalty_card = 1 THEN 1 ELSE 0 END AS discount_applies,
                ROUND(((CASE WHEN (COALESCE(SUM(m.price),0) > 100 OR o.has_loyalty_card=1)
                    THEN COALESCE(SUM(m.price),0) * 0.95 ELSE COALESCE(SUM(m.price),0) END)
                    + CASE WHEN o.service_type=1 THEN 8.0 ELSE 0 END) * 1.1, 2) AS final_total
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN menu m ON m.id = oi.menu_item_id
            GROUP BY o.id;
            """
        )

    def _seed_menu(self):
        """seed default pizzas once"""
        pizzas = [
            ("Pepperoni", 21.00),
            ("Chicken Supreme", 23.50),
            ("BBQ Meatlovers", 25.50),
            ("Veg Supreme", 22.50),
            ("Hawaiian", 19.00),
            ("Margherita", 18.50),
        ]
        self.conn.executemany(
            """--sql
            INSERT OR IGNORE INTO menu(name, price) VALUES(?, ?);
            """,
            pizzas
        )

    def _seed_default_user(self):
        """create a default admin user if missing"""
        self.conn.execute(
            """--sql
            INSERT OR IGNORE INTO accounts(username, password, privilege_level)
            VALUES (?,?,?)
            """,
            ("admin", "admin", AccountManager.PrivilegeLevel.ADMIN.value)
        )

    def reset_database(self):
        """danger: wipe everything; user must confirm"""
        ans = input(colored("reset database? this deletes ALL data. (y/N): ", "red"))
        if not parse_boolean_input(ans):
            cprint("cancelled", "yellow")
            return
        self.conn.executescript(
            """--sql
            DROP TABLE IF EXISTS order_items;
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS menu;
            DROP TABLE IF EXISTS accounts;
            DROP VIEW IF EXISTS order_totals;
            """
        )
        cprint("database cleared (restart program to reseed)", "green")
        sys.exit(0)

# accounts/auth
class AccountManager:
    """manage user accounts and session state (plain text passwords accepted because assignment)"""
    class PrivilegeLevel(Enum):
        USER = 0
        ADMIN = 1

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.current_user_id: int | None = None

    @property
    def current_privilege(self) -> int:
        """return privilege of current session user (0 if none)"""
        if self.current_user_id is None:
            return 0
        row = self.db.conn.execute(
            "SELECT privilege_level FROM accounts WHERE id=? LIMIT 1;",
            (self.current_user_id,)
        ).fetchone()
        return row["privilege_level"] if row else 0

    def _reset_session(self):
        """clear session user id"""
        self.current_user_id = None

    def is_admin(self):
        """true if current user is admin"""
        return self.current_privilege == AccountManager.PrivilegeLevel.ADMIN.value

    def require_admin(self):
        """guard for admin-only actions"""
        if self.current_user_id is None:
            cprint("please login first", "red"); return False
        if not self.is_admin():
            cprint("admin privileges required", "red"); return False
        return True

    def _login(self, username: str, password: str) -> bool:
        """internal credential check"""
        user = self.db.conn.execute(
            "SELECT id, privilege_level FROM accounts WHERE username=? AND password=?;",
            (username, password)
        ).fetchone()
        if not user:
            return False
        self.current_user_id = user["id"]
        level_name = AccountManager.PrivilegeLevel(user["privilege_level"]).name.lower()
        prefix = f"{level_name}: " if level_name != "user" else ""
        cprint(f"logged in as {prefix}{colored(username, 'yellow', attrs=['bold'])}", "green")
        return True

    def login(self, username: str | None = None, password: str | None = None):
        """interactive login (or non-interactive if args provided)"""
        if self.current_user_id is not None:
            cprint("already logged in", "yellow")
            ans = input("log out first? (y/N): ")
            if parse_boolean_input(ans):
                self.logout()
            else:
                return
        if username and password:
            if not self._login(username, password):
                cprint("invalid username or password", "red")
            return
        while True:
            user = input(colored("username: ", "magenta")).strip()
            pwd = input(colored("password: ", "magenta")).strip()
            if self._login(user, pwd):
                break
            cprint("invalid username or password", "red")

    def logout(self):
        """log out current user"""
        if self.current_user_id is None:
            cprint("no user logged in", "red")
            return
        cprint(f"logged out user #{self.current_user_id}", "green")
        self._reset_session()

    def user_exists(self, username: str) -> bool:
        """check if username exists"""
        return self.db.conn.execute(
            "SELECT 1 FROM accounts WHERE username=? LIMIT 1;",
            (username,)
        ).fetchone() is not None

    def register(self, username: str | None = None, password: str | None = None):
        """create new account (admin can optionally grant admin)"""
        if username is None:
            username = input(colored("choose a username: ", "magenta")).strip()
        if password is None:
            password = input(colored("choose a password: ", "magenta")).strip()
        if not (3 <= len(username) <= 20) or not username.isalnum():
            cprint("username must be 3-20 chars and alphanumeric", "red"); return
        if len(password) < 4:
            cprint("password too short (min 4)", "red"); return
        if self.user_exists(username):
            cprint("username already taken", "red"); return
        level = AccountManager.PrivilegeLevel.USER
        if self.is_admin():
            ans = input(f"set new user as admin? {colored('(dangerous)', 'red')} (y/N): ")
            if parse_boolean_input(ans):
                level = AccountManager.PrivilegeLevel.ADMIN
        self.db.conn.execute(
            "INSERT INTO accounts(username, password, privilege_level) VALUES(?,?,?);",
            (username, password, level.value)
        )
        cprint("account created", "green")

    def register_or_login(self, username: str | None = None, password: str | None = None):
        """prompt user to pick register / login"""
        ans = input(f"would you like to ({colored('r','light_blue')})egister or ({colored('l','light_blue')})ogin?: ").strip().lower()
        if ans == "r":
            self.register(username, password)
        elif ans == "l":
            self.login(username, password)
        else:
            cprint("invalid option", "red")

    def whoami(self):
        """print current user identity"""
        if self.current_user_id is None:
            cprint("no user currently logged in", "red"); return
        user = self.db.conn.execute(
            "SELECT username, privilege_level FROM accounts WHERE id=?;",
            (self.current_user_id,)
        ).fetchone()
        if not user:
            cprint("error fetching user info", "red"); return
        level = AccountManager.PrivilegeLevel(user["privilege_level"]).name.lower()
        prefix = f"{level}: " if level != "user" else ""
        cprint(f"you are logged in as {prefix}{colored(user['username'],'yellow',attrs=['bold'])}", "green")

# domain models
class OrderItem(ABC):
    """abstract orderable item type"""
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def price(self) -> float: ...

@dataclass
class Pizza(OrderItem):
    """pizza model"""
    _name: str
    _price: float
    @property
    def name(self) -> str: return self._name
    @property
    def price(self) -> float: return self._price

class ServiceType(Enum):
    """pickup or delivery"""
    PICKUP = 0
    DELIVERY = 1

@dataclass
class Order:
    """in-memory order representation (db-backed)"""
    id: int
    items: list[OrderItem]
    service_type: ServiceType
    has_loyalty_card: bool
    is_discounted: bool = False
    paid: bool = False

    @property
    def raw_cost(self):
        """sum of item prices"""
        return sum(i.price for i in self.items)

    @property
    def total_cost(self):
        """compute final total including discount, delivery fee, gst"""
        base = self.raw_cost
        cost = base
        if base > DISCOUNT_THRESHOLD or self.has_loyalty_card:
            self.is_discounted = True
            cost = base * (1 - DISCOUNT_RATE)
        if self.service_type is ServiceType.DELIVERY:
            cost += DELIVERY_FEE
        return cost * (1 + GST_RATE)

# global menu cache
menu: list[OrderItem] = []

def reload_menu(order_manager: "OrderManager"):
    """reload global menu cache from db"""
    global menu
    menu = [Pizza(r["name"], r["price"]) for r in order_manager.fetch_menu()]

# order management
class OrderManager:
    """manage orders, items, payments, reports"""
    def __init__(self, db: DatabaseManager, account_manager: AccountManager):
        self.db = db
        self.account_manager = account_manager
        self.orders: list[Order] = []
        self.current_order_id: int | None = None
        reload_menu(self)
        self._refresh_orders()

    # internal loading
    def _refresh_orders(self):
        """refresh in-memory order list"""
        self.orders.clear()
        for row in self._query_orders():
            items = [Pizza(r["name"], r["price"]) for r in self.fetch_items_for_order(row["id"])]
            self.orders.append(
                Order(
                    id=row["id"],
                    items=items,
                    service_type=ServiceType(row["service_type"]),
                    has_loyalty_card=bool(row["has_loyalty_card"]),
                    is_discounted=bool(row["is_discounted"]),
                    paid=bool(row["paid"])
                )
            )

    def _query_orders(self, paid_only: bool = False) -> Sequence[sqlite3.Row]:
        """get order rows filtered by user / paid status"""
        paid_clause = "AND paid=1" if paid_only else ""
        if self.account_manager.is_admin():
            return self.db.conn.execute(
                f"SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE 1=1 {paid_clause} ORDER BY id;"
            ).fetchall()
        uid = self.account_manager.current_user_id
        return self.db.conn.execute(
            f"SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE customer_id=? {paid_clause} ORDER BY id;",
            (uid,)
        ).fetchall()

    # menu queries
    def fetch_menu(self):
        """return menu rows"""
        return self.db.conn.execute("SELECT name, price FROM menu ORDER BY id;").fetchall()

    def get_menu_item(self, name: str):
        """lookup a menu item by case-insensitive name"""
        return self.db.conn.execute(
            "SELECT id, name, price FROM menu WHERE lower(name)=lower(?);",
            (name,)
        ).fetchone()

    # order db ops
    def insert_order(self, service_type: int, has_loyalty: bool) -> int:
        """create new order record"""
        customer_id = self.account_manager.current_user_id
        cur = self.db.conn.execute(
            "INSERT INTO orders(customer_id, service_type, has_loyalty_card) VALUES(?,?,?);",
            (customer_id, service_type, int(has_loyalty))
        )
        return cur.lastrowid

    def delete_order(self, order_id: int):
        """delete order by id"""
        self.db.conn.execute("DELETE FROM orders WHERE id=?;", (order_id,))

    def fetch_order_by_id(self, order_id: int):
        """get order row"""
        return self.db.conn.execute(
            "SELECT id, customer_id, service_type, has_loyalty_card, is_discounted, paid FROM orders WHERE id=?;",
            (order_id,)
        ).fetchone()

    def fetch_items_for_order(self, order_id: int):
        """get item rows for order"""
        return self.db.conn.execute(
            """--sql
            SELECT menu.name, menu.price
            FROM order_items
            JOIN menu ON menu.id = order_items.menu_item_id
            WHERE order_items.order_id=?
            ORDER BY order_items.id;
            """,
            (order_id,)
        ).fetchall()

    def update_paid_and_discount(self, order_id: int, paid: bool, discounted: bool):
        """update paid + discount flags"""
        self.db.conn.execute(
            "UPDATE orders SET paid=?, is_discounted=? WHERE id=?;",
            (int(paid), int(discounted), order_id)
        )

    # item helpers
    def _db_add_order_item(self, order_id: int, menu_name: str):
        """add a single menu item to order (db only)"""
        menu_row = self.get_menu_item(menu_name)
        if not (self.fetch_order_by_id(order_id) and menu_row):
            return False
        self.db.conn.execute(
            "INSERT INTO order_items(order_id, menu_item_id) VALUES(?,?);",
            (order_id, menu_row["id"])
        )
        return True

    def _db_remove_order_item(self, order_id: int, menu_name: str):
        """remove one instance of item from order (db only)"""
        menu_row = self.get_menu_item(menu_name)
        if not (self.fetch_order_by_id(order_id) and menu_row):
            return False
        self.db.conn.execute(
            """--sql
            DELETE FROM order_items
            WHERE rowid IN (
                SELECT rowid FROM order_items
                WHERE order_id=? AND menu_item_id=?
                LIMIT 1
            );
            """,
            (order_id, menu_row["id"])
        )
        return True

    # order selection
    def _get_order(self, oid: int | None):
        """return order object by id or none"""
        return next((o for o in self.orders if o.id == oid), None)

    def _ensure_current_order(self):
        """ensure a mutable current order is selected (prompt user if not)"""
        order = self._get_order(self.current_order_id)
        if order is None:
            cprint("no current order selected", "yellow")
            if self.orders:
                ans = input("select an order? (y/N): ")
                if parse_boolean_input(ans):
                    self.switch_order()
            else:
                ans = input("create an order? (y/N): ")
                if parse_boolean_input(ans):
                    self.create_order()
            return None
        if order.paid:
            cprint("order already paid", "yellow")
            ans = input("switch to another? (y/N): ")
            if parse_boolean_input(ans):
                self.switch_order()
            return None
        return order

    # public actions
    def list_orders(self):
        """list visible orders"""
        if not self.orders:
            cprint("no orders found", "red"); return
        for o in self.orders:
            self.print_order(o)

    def print_order(self, order: Order):
        """print single order summary"""
        cprint(f"order #{order.id} ({order.service_type.name.lower()}):", "green")
        print("\titems:", ", ".join(i.name for i in order.items) or "none")
        print("\tservice type:", order.service_type.name)
        print("\ttotal cost:", f"${order.total_cost:.2f}")
        print("\tpaid:", "yes" if order.paid else "no")

    def create_order(self, type: str | None = None):
        """create and select a new order"""
        if type is None:
            type = input("order type? (pickup/delivery): ").strip().lower()
        try:
            service_type = ServiceType[type.upper()]
        except KeyError:
            cprint("invalid service type", "red"); return
        ans = input("does customer have a loyalty card? (y/N): ")
        has_loyalty = parse_boolean_input(ans)
        oid = self.insert_order(service_type.value, has_loyalty)
        self._refresh_orders()
        self.current_order_id = oid
        cprint(f"order #{oid} created", "green")

    def remove_order(self):
        """remove an order by id (own or any if admin)"""
        self.list_orders()
        if not self.orders:
            return
        raw = input("enter order id to remove: ").strip()
        oid = safe_int(raw, minimum=1)
        if oid is None:
            cprint("invalid order id", "red"); return
        order = self._get_order(oid)
        if not order:
            cprint("order not found", "red"); return
        if not self.account_manager.is_admin():
            row = self.fetch_order_by_id(oid)
            if row and row["customer_id"] != self.account_manager.current_user_id:
                cprint("cannot remove another user's order", "red"); return
        self.delete_order(oid)
        if self.current_order_id == oid:
            self.current_order_id = None
        self._refresh_orders()
        cprint(f"order #{oid} removed", "green")

    def switch_order(self):
        """switch active order id"""
        self.list_orders()
        if not self.orders:
            return
        raw = input("enter order id to switch: ").strip()
        oid = safe_int(raw, minimum=1)
        if oid is None:
            cprint("invalid id", "red"); return
        if not self._get_order(oid):
            cprint("order not found", "red"); return
        if self.current_order_id == oid:
            cprint("already current order", "yellow"); return
        self.current_order_id = oid
        cprint(f"switched to order #{oid}", "green")

    def add_order_item(self, item: str | None = None, quantity: str | None = "1"):
        """add menu item(s) to current order"""
        if item is None:
            item = input("menu item to add: ").strip().lower()
        chosen = next((m for m in menu if m.name.lower() == item.lower()), None)
        if chosen is None:
            cprint("invalid menu item", "red"); return
        qty = safe_int(quantity or "1", minimum=1)
        if qty is None:
            raw = input("enter quantity (>=1): ")
            qty = safe_int(raw, minimum=1)
            if qty is None:
                cprint("invalid quantity", "red"); return
        if qty > MAX_BATCH_ITEM_ADD:
            cprint(f"max quantity {MAX_BATCH_ITEM_ADD} at a time", "red"); return
        order = self._ensure_current_order()
        if not order:
            return
        for _ in range(qty):
            if not self._db_add_order_item(order.id, chosen.name):
                cprint("db failure adding item", "red"); return
            order.items.append(chosen)
        cprint(f"added {qty} x {chosen.name} to order #{order.id}", "green")

    def remove_order_item(self):
        """remove one or more instances of a menu item from current order"""
        order = self._ensure_current_order()
        if not order:
            return
        name = input("menu item to remove: ").strip().lower()
        chosen = next((m for m in menu if m.name.lower() == name), None)
        if chosen is None:
            cprint("invalid menu item", "red"); return
        qraw = input("how many to remove?: ").strip()
        qty = safe_int(qraw, minimum=1)
        if qty is None:
            cprint("invalid quantity", "red"); return
        removed = 0
        for _ in range(qty):
            if self._db_remove_order_item(order.id, chosen.name):
                for i, itm in enumerate(order.items):
                    if itm.name == chosen.name:
                        del order.items[i]
                        removed += 1
                        break
        if removed:
            cprint(f"removed {removed} x {chosen.name}", "green")
        else:
            cprint("item not found in order", "red")

    def process_order(self):
        """finalise and pay current order"""
        order = self._ensure_current_order()
        if not order:
            return
        if order.paid:
            cprint("order already paid", "red"); return
        total = order.total_cost
        extras = []
        if order.is_discounted:
            extras.append("5% discount")
        if order.service_type is ServiceType.DELIVERY:
            extras.append(f"{color_money(DELIVERY_FEE)} delivery")
        extras.append(f"{int(GST_RATE*100)}% gst")
        extras_str = ", including " + " and ".join(extras)
        print(f"total for order #{order.id} is {color_money(total)}{extras_str}.")
        ans = input("pay now? (y/N): ")
        if parse_boolean_input(ans):
            order.paid = True
            self.update_paid_and_discount(order.id, True, order.is_discounted)
            cprint("payment successful", "green")
        else:
            cprint("payment cancelled", "yellow")

    def generate_daily_sales_summary(self):
        """print paid orders and aggregate total (user-scoped unless admin)"""
        rows = self._query_orders(paid_only=True)
        if not rows:
            cprint("no sales", "red"); return
        total = 0.0
        for row in rows:
            items = [Pizza(r["name"], r["price"]) for r in self.fetch_items_for_order(row["id"])]
            temp = Order(
                id=row["id"],
                items=items,
                service_type=ServiceType(row["service_type"]),
                has_loyalty_card=bool(row["has_loyalty_card"]),
                is_discounted=bool(row["is_discounted"]),
                paid=True
            )
            amt = temp.total_cost
            total += amt
            owner = f" (user #{row['customer_id']})" if self.account_manager.is_admin() else ""
            print(f"order #{temp.id}{owner}: {color_money(amt)}")
        cprint(f"total sales: {color_money(total)}", "green")

    # admin reports
    def admin_report_revenue_by_user(self):
        """report total paid revenue grouped by user"""
        if not self.account_manager.require_admin():
            return
        rows = self.db.conn.execute(
            """--sql
            SELECT COALESCE(a.username,'guest') AS username,
                   COUNT(o.id) AS order_count,
                   SUM(ot.final_total) AS total_revenue
            FROM order_totals ot
            JOIN orders o ON o.id = ot.order_id
            LEFT JOIN accounts a ON a.id = o.customer_id
            WHERE o.paid = 1
            GROUP BY o.customer_id
            ORDER BY total_revenue DESC;
            """
        ).fetchall()
        if not rows:
            cprint("no data", "red"); return
        cprint("revenue by user", "green", attrs=["bold"])
        for r in rows:
            print(f"{r['username']}: {r['order_count']} orders -> {color_money(r['total_revenue'])}")

    def admin_report_top_menu_items(self):
        """report top-selling menu items"""
        if not self.account_manager.require_admin():
            return
        rows = self.db.conn.execute(
            """--sql
            SELECT m.name, COUNT(oi.id) AS times_ordered, ROUND(SUM(m.price),2) AS revenue
            FROM order_items oi
            JOIN menu m ON m.id = oi.menu_item_id
            JOIN orders o ON o.id = oi.order_id
            WHERE o.paid=1
            GROUP BY m.id
            ORDER BY times_ordered DESC, m.name ASC
            LIMIT 10;
            """
        ).fetchall()
        if not rows:
            cprint("no data", "red"); return
        cprint("top menu items", "green", attrs=["bold"])
        for r in rows:
            print(f"{r['name']}: {r['times_ordered']} sold -> {color_money(r['revenue'])}")

    def admin_report_average_order_value(self):
        """report avg/min/max paid order value"""
        if not self.account_manager.require_admin():
            return
        r = self.db.conn.execute(
            """--sql
            SELECT ROUND(AVG(final_total),2) AS avg_value,
                   ROUND(MIN(final_total),2) AS min_value,
                   ROUND(MAX(final_total),2) AS max_value,
                   COUNT(*) AS paid_orders
            FROM order_totals
            WHERE paid=1;
            """
        ).fetchone()
        cprint("order value stats", "green", attrs=["bold"])
        if r and r["paid_orders"]:
            print(f"orders: {r['paid_orders']} | avg {color_money(r['avg_value'])} | "
                  f"min {color_money(r['min_value'])} | max {color_money(r['max_value'])}")
        else:
            print("no paid orders")

    def admin_report_discount_usage(self):
        """report discount adoption rate"""
        if not self.account_manager.require_admin():
            return
        r = self.db.conn.execute(
            """--sql
            SELECT SUM(CASE WHEN is_discounted=1 THEN 1 ELSE 0 END) AS discounted,
                   COUNT(*) AS total
            FROM orders;
            """
        ).fetchone()
        if not r or r["total"] == 0:
            cprint("no orders", "red"); return
        pct = (r["discounted"] / r["total"]) * 100
        cprint("discount usage", "green", attrs=["bold"])
        print(f"{r['discounted']} / {r['total']} orders ({pct:.1f}%) received a discount")

    # admin account/menu management
    def admin_list_accounts(self):
        """list all accounts"""
        if not self.account_manager.require_admin():
            return
        rows = self.db.conn.execute(
            "SELECT id, username, privilege_level FROM accounts ORDER BY id;"
        ).fetchall()
        for r in rows:
            role = "admin" if r["privilege_level"] == 1 else "user"
            print(f"#{r['id']}: {r['username']} ({role})")

    def admin_promote(self, user_id: str):
        """promote user to admin"""
        if not self.account_manager.require_admin():
            return
        if not user_id.isdigit():
            cprint("invalid id", "red"); return
        self.db.conn.execute("UPDATE accounts SET privilege_level=1 WHERE id=?;", (int(user_id),))
        cprint("promoted", "green")

    def admin_demote(self, user_id: str):
        """demote admin to user"""
        if not self.account_manager.require_admin():
            return
        if not user_id.isdigit():
            cprint("invalid id", "red"); return
        self.db.conn.execute("UPDATE accounts SET privilege_level=0 WHERE id=?;", (int(user_id),))
        cprint("demoted", "green")

    def admin_menu_add(self, name: str | None = None, price: str | None = None):
        """add a menu item"""
        if not self.account_manager.require_admin():
            return
        if name is None:
            name = input("menu item name: ").strip()
        if price is None:
            price = input("price: ").strip()
        try:
            p = float(price)
            if p <= 0: raise ValueError
        except Exception:
            cprint("invalid price", "red"); return
        try:
            self.db.conn.execute("INSERT INTO menu(name, price) VALUES(?,?);", (name, p))
            reload_menu(self)
            cprint("menu item added", "green")
        except Exception as e:
            cprint(f"failed: {e}", "red")

    def admin_menu_update_price(self, name: str | None = None, price: str | None = None):
        """update price of a menu item"""
        if not self.account_manager.require_admin():
            return
        if name is None:
            name = input("menu item name: ").strip()
        if price is None:
            price = input("new price: ").strip()
        try:
            p = float(price)
            if p <= 0: raise ValueError
        except Exception:
            cprint("invalid price", "red"); return
        cur = self.db.conn.execute(
            "UPDATE menu SET price=? WHERE lower(name)=lower(?);",
            (p, name)
        )
        if cur.rowcount:
            reload_menu(self)
            cprint("updated", "green")
        else:
            cprint("not found", "red")

    def admin_menu_delete(self, name: str | None = None):
        """delete a menu item"""
        if not self.account_manager.require_admin():
            return
        if name is None:
            name = input("menu item name: ").strip()
        cur = self.db.conn.execute(
            "DELETE FROM menu WHERE lower(name) LIKE lower(?);",
            (name,)
        )
        if cur.rowcount:
            reload_menu(self)
            cprint("deleted", "green")
        else:
            cprint("not found", "red")

# command infrastructure
class Command:
    """bind a command name to a function"""
    def __init__(self, name: str, function: Callable, description: str,
                 privilege_level: AccountManager.PrivilegeLevel | None = AccountManager.PrivilegeLevel.USER):
        self.name = name
        self._fn = function
        self.description = description
        self.privilege_level = privilege_level

    def execute(self, tokens: list[str]):
        """validate arg count and invoke function"""
        sig = inspect.signature(self._fn)
        params = list(sig.parameters.values())
        required = sum(
            p.default == inspect._empty and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY
            )
            for p in params
        )
        if not (required <= len(tokens) <= len(params)):
            cprint(f"invalid args for '{self.name}' (expected {required}-{len(params)}, got {len(tokens)})", "red")
            return
        return self._fn(*tokens)

class CommandParser:
    """simple repl parser"""
    def __init__(self, account_manager: AccountManager):
        self.account_manager = account_manager
        self.commands: list[Command] = [
            Command("help", self.show_help, "show this help", None),
            Command("h", self.show_help, "alias help", None),
            Command("quit", self.quit, "exit program", None),
            Command("exit", lambda: cprint("use quit to exit", "yellow"), "alias quit", None),
        ]

    def parse_and_execute(self, input_str: str):
        """parse the raw input string and attempt to execute a command"""
        tokens = input_str.strip().split()
        if not tokens:
            return
        for cmd in self.commands:
            parts = cmd.name.split()
            if tokens[:len(parts)] != parts:
                continue
            if cmd.privilege_level is not None and self.account_manager.current_user_id is None:
                cprint("please login/register first", "yellow")
                self.account_manager.register_or_login()
                print("\n")
            if cmd.privilege_level is not None and self.account_manager.current_user_id is None:
                cprint("authentication required", "red"); return
            if (cmd.privilege_level == AccountManager.PrivilegeLevel.ADMIN
                and not self.account_manager.is_admin()):
                cprint("insufficient privileges", "red"); return
            args = tokens[len(parts):]
            return cmd.execute(args)
        cprint("unknown command. type 'help'", "red")

    def show_help(self):
        """display help with all available command names and descriptions"""
        cprint("available commands:", "green", attrs=["bold"])
        width = max(len(c.name) for c in self.commands)
        for cmd in self.commands:
            if (cmd.privilege_level == AccountManager.PrivilegeLevel.ADMIN
                and not self.account_manager.is_admin()):
                continue
            sig = inspect.signature(cmd._fn)
            params = " ".join(
                f"<{p}>" if prm.default == inspect._empty else f"[{p}]"
                for p, prm in sig.parameters.items()
            )
            line = f"{colored(cmd.name,'blue')} {colored(params,'cyan')}".strip()
            print(line.ljust(width + 25), "-", cmd.description)

    @staticmethod
    def quit():
        """interactive quit confirmation"""
        ans = input(colored("are you sure you want to quit? (y/N): ", "yellow"))
        if parse_boolean_input(ans):
            cprint("okay, see ya!", "green")
            sys.exit(0)
        cprint("continuing...", "green")

    def start_repl(self):
        """main repl loop"""
        while True:
            try:
                user_input = input(colored("\n> ", "blue")).strip()
            except EOFError:
                print()
                break
            if user_input:
                self.parse_and_execute(user_input)

# application wiring
class Application:
    """bootstrap objects & start repl"""
    def __init__(self, *args: str):
        self.db = DatabaseManager()
        atexit.register(lambda: self.db.conn.close() if self.db.conn else None)
        self.account_manager = AccountManager(self.db)
        self.order_manager = OrderManager(self.db, self.account_manager)
        parser = CommandParser(self.account_manager)

        # user commands
        parser.commands += [
            Command("menu", self.show_menu, "show menu"),
            Command("order create", self.order_manager.create_order, "create order"),
            Command("order remove", self.order_manager.remove_order, "remove order"),
            Command("order list", self.order_manager.list_orders, "list orders"),
            Command("order process", self.order_manager.process_order, "pay current order"),
            Command("order switch", self.order_manager.switch_order, "switch current order"),
            Command("order item add", self.order_manager.add_order_item, "add item"),
            Command("order item remove", self.order_manager.remove_order_item, "remove item"),
            Command("order summary", self.order_manager.generate_daily_sales_summary, "sales summary"),
            Command("account whoami", self.account_manager.whoami, "current user", None),
            Command("account login", self.account_manager.login, "login", None),
            Command("account logout", self.account_manager.logout, "logout", None),
            Command("account register", self.account_manager.register, "register", None),
        ]

        # admin commands
        parser.commands += [
            Command("admin accounts list", self.order_manager.admin_list_accounts, "list accounts", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin accounts promote", self.order_manager.admin_promote, "promote user", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin accounts demote", self.order_manager.admin_demote, "demote user", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin menu add", self.order_manager.admin_menu_add, "add menu item", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin menu update", self.order_manager.admin_menu_update_price, "update menu price", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin menu delete", self.order_manager.admin_menu_delete, "delete menu item", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin report revenue", self.order_manager.admin_report_revenue_by_user, "revenue by user", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin report top-items", self.order_manager.admin_report_top_menu_items, "top items", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin report stats", self.order_manager.admin_report_average_order_value, "order stats", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin report discount", self.order_manager.admin_report_discount_usage, "discount usage", AccountManager.PrivilegeLevel.ADMIN),
            Command("admin db reset", self.db.reset_database, "reset database", AccountManager.PrivilegeLevel.ADMIN),
        ]

        cprint("""
welcome to papa-pizza, the sequel!!! 🍕,
your local pizza store's customer database!
           
by vapidinfinity, aka esi
    """, "green", attrs=["bold"])

        print("""this is a simple command line interface for managing customers in papa-pizza, the world-renowned pseudo pizza store
              
for more information, type 'help' or 'h' at any time.
to exit the program, type 'quit' or 'exit'.""")

        if args:
            parser.parse_and_execute(" ".join(args))
        parser.start_repl()

    @staticmethod
    def show_menu():
        """print cached menu grouped by item class"""
        cprint("papa-pizza's famous menu", None, attrs=["bold"])
        if not menu:
            cprint("menu empty", "red"); return
        current_type = None
        for item in menu:
            t = type(item).__name__
            if t != current_type:
                current_type = t
                cprint(f"\n{t}:", "green", attrs=["bold"])
            cprint(f"{item.name}: ${item.price:.2f}", "green")

# entry point
def main():
    """entrypoint wrapper"""
    args = sys.argv[1:]
    Application(*args)

# signal handler
class SignalHandler:
    """custom ctrl+c handler to nag user politely"""
    @staticmethod
    def sigint(_, __):
        """handle ctrl+c"""
        cprint("\nnext time, use quit!", "yellow")
        sys.exit(0)

signal.signal(signal.SIGINT, SignalHandler.sigint)

if __name__ == "__main__":
    main()
**THIS IS NOT RELATED TO THE ASSIGNMENT, BELOW IS AN AI-GENERATED MANUAL ON HOW TO USE THE SCRIPT BECAUSE IT'S SO OVERENGINEERED**

# `papa-pizza-db` — User Manual

## 1. Default Account

- Username: admin
- Password: admin
- Change / create others after login.
- All new users are regular (non-admin) unless promoted.

---

## 2. Core Concepts

| Concept | Notes |
|--------|-------|
| Account | username, password (plain text), privilege (user/admin) |
| Menu | Seeded pizzas; admins can modify |
| Order | Belongs to user (nullable), has items, service type, loyalty flag |
| Order Items | Each references a menu item |
| Discounts | 5% if (raw total > 100) OR loyalty card |
| Delivery | Flat $8 fee on delivery orders |
| GST | 10% applied last |
| Paid Flag | Marks order final; cannot be modified further |

---

## 3. Cost Calculation (order.total_cost)
Order Flow: raw sum -> optional 5% discount -> add delivery fee (if delivery) -> add 10% GST.

---

## 4. Starting the Program

```
python main.py
```

Type `help` (or `h`) any time.

Exit with `quit` (preferred) or Ctrl+C (will warn).

---

## 5. Typical User Workflow

1. `account register` (or login as admin)
2. `menu` (view items)
3. `order create` (choose pickup/delivery + loyalty)
4. `order item add Pepperoni 2`
5. Repeat adds / removals
6. `order process` (pay)
7. `order summary` (view paid totals for your account)

---

## 6. Command Reference (Grouped)

### General
| Command | Description |
|---------|-------------|
| help / h | Show all available commands |
| quit | Exit with confirmation |
| menu | Show current menu |

### Account
| Command | Description |
|---------|-------------|
| account register | Register new user |
| account login | Login existing user |
| account logout | Logout current session |
| account whoami | Show current user |

### Orders
| Command | Description |
|---------|-------------|
| order create | Create new order (prompts: pickup/delivery & loyalty) |
| order switch | Switch active order |
| order list | List your (or all if admin) orders |
| order remove | Delete an order (must own unless admin) |
| order item add <name> [qty] | Add item(s) to current order |
| order item remove | Interactive removal |
| order process | Finalize & mark paid |
| order summary | Show paid orders + aggregate (user scoped unless admin) |

### Admin – Accounts
| Command | Description |
|---------|-------------|
| admin accounts list | List all accounts |
| admin accounts promote [id] | Promote a user |
| admin accounts demote [id] | Demote an admin (not last one) |

### Admin – Menu
| Command | Description |
|---------|-------------|
| admin menu add | Add menu item (name + price) |
| admin menu update | Update price |
| admin menu delete | Delete item |

### Admin – Reports
| Command | Description |
|---------|-------------|
| admin report revenue | Revenue grouped by user |
| admin report top-items | Top-selling menu items |
| admin report stats | Average / min / max order value |
| admin report discount | Discount usage rate |

### Admin – Maintenance
| Command | Description |
|---------|-------------|
| admin db reset | Wipes ALL tables (asks confirmation) |

---

## 7. Examples

Create delivery order with loyalty:
```
order create
order item add "Pepperoni" 2
order item add "Margherita"
order list
order process
```

Fast add with inline args:
```
order item add Hawaiian 3
```

Promote a user (admin):
```
admin accounts list
admin accounts promote 3
```

Add a new menu item:
```
admin menu add
(menu item name: Four Cheese)
(price: 24.5)
```

---

## 8. Discounts & Flags

| Condition | Effect |
|-----------|--------|
| Raw total > 100 | 5% discount |
| Loyalty card = yes | 5% discount (even if < 100) |
| Delivery | + $8 fee |
| GST | Always applied last (10%) |

---

## 9. Data Persistence / Schema (Simplified)

Tables:
- accounts(id, username UNIQUE, password, privilege_level)
- menu(id, name UNIQUE, price>0 enforced by triggers)
- orders(id, customer_id FK nullable, service_type (0=pickup/1=delivery), has_loyalty_card, is_discounted, paid, created_at)
- order_items(id, order_id FK, menu_item_id FK)
- view: order_totals (precomputed financial summary per order)

---

## 10. Limitations / Notes

- Passwords stored in plain text (assignment simplification).
- No concurrency handling (single-user CLI).
- Max add quantity per command: 10.
- Discount flag stored when processed.
- Removing items after payment is blocked.

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| "unknown command" | Use `help` for list |
| Cannot add items | Ensure an unpaid current order (create / switch) |
| Discount not applied | Check raw total or loyalty flag |
| Permission denied | Login as admin |
| Menu empty | Possibly DB reset; restart to reseed |

---

## 12. Safety

Before `admin db reset`, export DB if needed:
```
sqlite3 papa-pizza.db ".backup backup.db"
```

---

## 13. Extending

Add new command:
1. Create method (e.g. in OrderManager or Application)
2. Append `Command("your name", fn, "desc", privilege)` to `parser.commands` in Application.

---

## 14. Exit

Use `quit` to exit cleanly (closes DB via atexit). Ctrl+C is caught.
# Papa-Pizza Data Management System  

## 1. Development Schedule (4 Weeks)

| Week | Tasks | Detail / Deliverables | Rationale |
|------|-------|-----------------------|-----------|
| 1 (Days 1–5) | Problem investigation | Define scenario, stakeholders, data needs, constraints, success criteria | Establish scope & feasibility |
| | Requirements gathering | Functional + database + non‑functional + compliance + stretch goals | Drives design validity |
| | Initial domain modeling | Draft entity list, interaction storyboard (ordering flow) | Align with processes |
| 2 (Days 6–10) | ERD (first pass – 5 entities) | Accounts, MenuItems, Orders, OrderItems, Payments | Normalised foundation |
| | Relational schema & data dictionary draft | Keys, datatypes, constraints | Ensures integrity upfront |
| | Risk & ethics analysis | Privacy, security, fairness, legal | Mandatory rubric coverage |
| 3 (Days 11–15) | Query planning (plain English) | Analytics + CRUD + reporting set | Ensures later SQL coverage |
| | Validation strategy | Dual-layer: DB constraints + Python guards | Data quality maximisation |
| | Refine design | Decide simplifications (e.g. fold Payments into Orders) | Pragmatic scope control |
| 4 (Days 16–20) | Design sign‑off documentation | Final ERD, relational notation, data dictionary | Frozen baseline |
| | Change log template | To justify implementation deviations | Rubric alignment |
| Buffer / Spill | Contingency & polish | Adjust for feasibility & performance | Quality assurance |


## 2. Problem Description (Scenario)

Papa-Pizza is a local store needing a simple system to:  
- Manage user/staff accounts (admin vs standard).  
- Record structured customer orders (pickup or delivery).  
- Calculate totals (GST, delivery fee, conditional discount).  
- Track payments (paid flag) and discount use.  
- Generate admin analytics (revenue by user, top items, order value stats, discount uptake).  

Problems with old process: arithmetic errors, lost order history, no insights, manual discount inconsistencies, inability to audit activity.  
Solution Goals: Accuracy, integrity, clear pricing logic, minimal friction, extensibility (future payment + loyalty expansion), and transparent reporting.

Stakeholders: Owner/Admin, Staff Operators, (Indirect) Customers, Auditor/Assessor.

Constraints: Python + SQLite only, CLI interface, local file DB, educational security scope (plaintext passwords acknowledged as limitation).

## 3. Requirements (MoSCoW)

### Must (implemented in code)
- User auth: register/login/logout (`account register/login/logout`).
- Role separation: admin vs user (privilege_level, `AccountManager.is_admin()`).
- View menu (`menu`) and seed default pizzas (`DatabaseManager._seed_menu`).
- Order lifecycle: create (`order create`), switch, list, add item (`order item add`), remove item (`order item remove`), pay (`order process`), delete (`order remove`).
- Pricing pipeline: discount threshold / loyalty, delivery fee, GST (see `Order.total_cost`, constants).
- Data integrity: FK ON, ON DELETE CASCADE (order_items), trigger rejects non‑positive price (`trg_menu_price_*`), UNIQUE usernames + menu names.
- Admin menu CRUD: add/update/delete (`admin menu add/update/delete`).
- Admin reports: revenue by user, top items, order value stats, discount usage (`admin report revenue/top-items/stats/discount`).
- Daily sales summary (`order summary`).
- Help system (`help` / `h`).
- Database view `order_totals` for derived totals (no stored redundant total).

### Should (implemented)
- Promote/demote users (`admin accounts promote/demote`).
- List accounts (`admin accounts list`).
- whoami (`account whoami`).
- Database reset (`admin db reset`).
- Colour output + friendly CLI (termcolor/colorama).
- Input safety: `safe_int`, bounded quantity (`MAX_BATCH_ITEM_ADD`).

### Could (not implemented yet)
- Export reports (CSV/JSON).
- Payment table (multi-method, audit trail).
- Password hashing (bcrypt/argon2).
- Quantity field instead of repeated rows.
- Audit/event log (per command).

### Won’t (out of scope this iteration)
- Real payment gateway.
- Multi-store / branches.
- Concurrency control / multi-terminal locking.
- Web or GUI frontend.
- Full immutable audit ledger.

## 4. Ethical / Legal / Security Issues

| Issue | Current Handling | Future Improvement |
|-------|------------------|--------------------|
| Plaintext passwords | Local only; minimal scope | Hash + salt |
| Pricing fairness | Single transparent rule | Configurable rules table |
| Data privacy | Only username stored | Retention policy |
| Tampering | FKs + triggers + recomputed view | Audit log |
| Tax accuracy (GST) | Centralised formula + final rounding | Multi-rate support |
| Role misuse | Explicit privilege checks on admin commands | Session logging |

## 5. Data Quality Factors

| Factor | Risk | Mitigation |
|--------|------|------------|
| Orphan line items | Broken totals | FK + ON DELETE CASCADE |
| Duplicate usernames/items | Ambiguous identity | UNIQUE constraints |
| Misapplied discount | Incorrect charges | Single cost function + view logic parity |
| Input typos | Invalid service type / quantity | Enum mapping + safe_int + bounds |
| Stale totals | Diverging stored sums | No stored final total; recompute via view |
| Floating point drift | Rounding inaccuracies | Round once at final output (2 dp) |
| Unauthorized deletion | Data loss | Ownership checks + admin gate |
| Over-large batch adds | Accidental bulk | MAX_BATCH_ITEM_ADD constant |

---

## 6. Traceability Snapshot (Example Mapping)
FR6 → `Order.total_cost()` + pricing constants + `order_totals` view  
DB2 → `trg_menu_price_insert` / `trg_menu_price_update`  
FR10–FR13 → Admin report methods (`admin_report_*`) in `OrderManager`  

---

## 7. Summary for Part 2 Alignment
All core FR/DB/NFR implemented except deferred stretch items (documented), preserving full marks justification.

## 8. Development Retrospective

### What Worked Well
- Early enforcement of foreign keys + triggers avoided downstream data fixes.
- Centralised pricing logic (`Order.total_cost` + `order_totals` view) eliminated duplication bugs.
- Separation of concerns (AccountManager / OrderManager / CommandParser) made later feature additions (reports, reset) low-friction.
- Using a view for financial aggregation simplified complex report SQL.

### What Didn’t Work Well
- Initial inclusion of a Payment entity added complexity without rubric benefit; removed mid‑design.
- Plaintext password decision postponed security thinking; retrofitting hashing now would touch multiple code paths.
- Repeated rows for quantities inflated potential row counts and required extra aggregation in reports.
- Lack of unit tests slowed confidence when refactoring pricing & discount logic.
- Rewriting original `papa-pizza` codebase, modularity comes at a cost when most modules need rewriting

### Changes From Initial Design
- Payment table removed; replaced by `paid` flag and derived totals (documented trade-off).
- Quantity column omitted; using multiple identical order_items rows (simpler insertion, less efficient).
- Added `order_totals` view (not originally listed) for cleaner analytics and to avoid storing redundant totals.

### Known Limitations / Bugs
- No password hashing (security limitation).
- No atomic multi-item transaction batching (minor risk if interrupted mid-loop).
- Discount + loyalty logic is hard-coded (needs config table for future flexibility).
- No audit trail for admin destructive actions (e.g. menu delete, db reset).
- `safe_int` lacks explicit error message context per field.

### Improvement Plan (Future Iteration)
1. Introduce hashed passwords (bcrypt) + migration of existing entries.
2. Add Payment table (method, amount, timestamp) to support partial/mixed payments.
3. Replace repeated line items with (order_id, menu_item_id, quantity) + constraint enforcing quantity > 0.
4. Implement export/report module (CSV + JSON) and automated unit tests for pricing and discount edge cases.
5. Add audit_log table (timestamp, user_id, action, payload JSON).
6. Parameterize discount rules (table-driven thresholds and rates).

### Process Reflection
- Front-loaded modelling reduced rework; only one schema pivot (Payment removal).
- Lack of lightweight tests was primary friction; next time: write tests immediately after implementing pricing function.
- Using MoSCoW early increased decisiveness during time trade-offs.
- Future: adopt brief daily log (time box) to capture rationale for micro design choices.

### Success Against Goals
| Goal | Result |
|------|--------|
| Integrity | Achieved: constraints + triggers + validation. |
| Accurate pricing | Verified with manual cases (discount + GST + delivery). |
| Reporting | Four analytic reports operational. |
| Extensibility | Payment + export pathways documented, modular managers. |
| Transparency | Single cost pathway + view ensures auditability. |

### Developer Lessons
- Start with minimal schema; only add entities when a concrete query or rule justifies them.
- Avoid building on existing applications that weren't intended to be used with SQL or that lack concrete database structure
- Derive instead of store when recalculation is inexpensive and avoids consistency drift.
- Document deferred features explicitly to avoid hidden technical debt.
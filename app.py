from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# ============================================================
# SMART WAREHOUSE OPERATIONS & ORDER FULFILLMENT SYSTEM
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "warehouse.db"

app = Flask(__name__)
app.secret_key = "smart-warehouse-hackathon-secret"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        location TEXT NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        reserved INTEGER NOT NULL DEFAULT 0,
        reorder_level INTEGER NOT NULL DEFAULT 10,
        reorder_qty INTEGER NOT NULL DEFAULT 25,
        unit_cost REAL NOT NULL DEFAULT 0,
        damaged INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no TEXT UNIQUE NOT NULL,
        customer TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'Medium',
        status TEXT NOT NULL DEFAULT 'Pending',
        sla_hours INTEGER NOT NULL DEFAULT 24,
        created_at TEXT NOT NULL,
        eta TEXT,
        notes TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        requested INTEGER NOT NULL,
        allocated INTEGER NOT NULL DEFAULT 0,
        picked INTEGER NOT NULL DEFAULT 0,
        packed INTEGER NOT NULL DEFAULT 0,
        dispatched INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
        FOREIGN KEY(product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS exceptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        decision TEXT,
        resolution TEXT,
        status TEXT NOT NULL DEFAULT 'Open',
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE SET NULL,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
    );
    """)

    # Ensure missing columns exist in orders table
    order_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
    if "qc_status" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN qc_status TEXT NOT NULL DEFAULT 'Pending'")
    if "allocated_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN allocated_at TEXT")
    if "picked_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN picked_at TEXT")
    if "packed_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN packed_at TEXT")
    if "qc_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN qc_at TEXT")
    if "dispatched_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN dispatched_at TEXT")

    # ========================================================
    # SAMPLE PRODUCTS
    # ========================================================

    products = [
        # IN STOCK
        ("SKU-1001", "Wireless Mechanical Keyboard", "Electronics", "A-01", 150, 10, 20, 50, 45.00, 2),
        ("SKU-1002", "Ergonomic Optical Mouse", "Electronics", "A-02", 200, 15, 30, 60, 25.00, 1),
        ("SKU-1003", "High-Speed USB-C Cable 2m", "Accessories", "B-01", 350, 20, 40, 100, 12.00, 3),
        ("SKU-1004", "Aluminum Laptop Stand", "Accessories", "B-02", 85, 5, 15, 30, 35.00, 0),

        # LOW STOCK
        ("SKU-1005", "4K Web Camera Pro", "Electronics", "C-01", 8, 6, 15, 25, 65.00, 1),
        ("SKU-1006", "Dual Monitor Arm Mount", "Furniture", "C-02", 5, 4, 10, 20, 85.00, 0),
        ("SKU-1007", "Noise Canceling Headset", "Audio", "D-01", 6, 5, 12, 25, 75.00, 1),

        # OUT OF STOCK (Stock = 0)
        ("SKU-1008", "Portable Power Bank 20000mAh", "Electronics", "D-02", 0, 0, 20, 30, 40.00, 0),
        ("SKU-1009", "Fast Wireless Charging Pad", "Electronics", "E-01", 0, 0, 15, 25, 20.00, 0),
        ("SKU-1010", "Smart LED Desk Lamp", "Home Office", "E-02", 0, 0, 10, 20, 30.00, 0)
    ]

    for p in products:
        conn.execute("""
            INSERT OR IGNORE INTO products
            (sku, name, category, location, stock, reserved, reorder_level, reorder_qty, unit_cost, damaged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, p)

    # ========================================================
    # SAMPLE ORDERS
    # ========================================================

    order_count = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    if order_count == 0:

        now = datetime.now()

        orders = [
            (
                "ORD-1001",
                "ABC Retail",
                "High",
                "Pending",
                12,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                (now + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
                "Priority customer"
            ),
            (
                "ORD-1002",
                "Tech World",
                "Medium",
                "Picking",
                24,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
                ""
            ),
            (
                "ORD-1003",
                "Smart Stores",
                "Low",
                "Dispatched",
                48,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                (now + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
                ""
            )
        ]

        conn.executemany("""
            INSERT INTO orders
            (
                order_no,
                customer,
                priority,
                status,
                sla_hours,
                created_at,
                eta,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, orders)

    conn.commit()
    conn.close()


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    conn = get_db()

    total_products = conn.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    total_stock = conn.execute(
        "SELECT COALESCE(SUM(stock), 0) FROM products"
    ).fetchone()[0]

    total_orders = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    pending_orders = conn.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE status IN ('Pending', 'Processing')
    """).fetchone()[0]

    picking_orders = conn.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE status = 'Picking'
    """).fetchone()[0]

    dispatched_orders = conn.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE status = 'Dispatched'
    """).fetchone()[0]

    low_stock = conn.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE stock <= reorder_level
    """).fetchone()[0]

    open_exceptions = conn.execute("""
        SELECT COUNT(*)
        FROM exceptions
        WHERE status = 'Open'
    """).fetchone()[0]

    recent_orders = conn.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    stats = {
        "total_products": total_products,
        "total_stock": total_stock,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "picking_orders": picking_orders,
        "dispatched_orders": dispatched_orders,
        "low_stock": low_stock,
        "open_exceptions": open_exceptions
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_orders=recent_orders
    )


# ============================================================
# ORDERS
# ============================================================

@app.route("/orders")
def orders():

    conn = get_db()

    all_orders = conn.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "orders.html",
        orders=all_orders
    )


# ============================================================
# NEW ORDER + PRODUCTS
# ============================================================

@app.route("/new-order", methods=["GET", "POST"])
def new_order():

    conn = get_db()

    # --------------------------------------------------------
    # GET ALL PRODUCTS
    # --------------------------------------------------------

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY name ASC
    """).fetchall()

    # --------------------------------------------------------
    # CREATE ORDER
    # --------------------------------------------------------

    if request.method == "POST":

        customer = request.form.get(
            "customer",
            ""
        ).strip()

        priority = request.form.get(
            "priority",
            "Medium"
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        # Customer validation

        if not customer:

            conn.close()

            flash(
                "Customer name is required.",
                "danger"
            )

            return redirect(
                url_for("new_order")
            )

        # ----------------------------------------------------
        # GET SELECTED PRODUCTS
        # ----------------------------------------------------

        product_ids = request.form.getlist(
            "product_id[]"
        )

        quantities = request.form.getlist(
            "quantity[]"
        )

        # If your HTML uses product_id instead of
        # product_id[], support that too.

        if not product_ids:
            product_ids = request.form.getlist(
                "product_id"
            )

        if not quantities:
            quantities = request.form.getlist(
                "quantity"
            )

        has_stockout = False
        valid_items = []

        for product_id, quantity in zip(product_ids, quantities):
            try:
                product_id = int(product_id)
                quantity = int(quantity)
            except (ValueError, TypeError):
                continue

            if quantity <= 0:
                continue

            product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if product is None:
                continue

            available = max(0, product["stock"] - product["reserved"])
            allocated = min(quantity, available)
            if allocated < quantity:
                has_stockout = True

            valid_items.append({
                "product_id": product_id,
                "requested": quantity,
                "allocated": allocated,
                "available": available,
                "name": product["name"]
            })

        if not valid_items:
            conn.close()
            flash("Please select at least one product and enter quantity.", "danger")
            return redirect(url_for("new_order"))

        next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM orders").fetchone()[0]
        order_no = f"ORD-{1000 + next_id}"
        now = datetime.now()
        eta = now + timedelta(hours=24)
        order_status = "Stockout" if has_stockout else "Pending"

        cursor = conn.execute("""
            INSERT INTO orders
            (order_no, customer, priority, status, sla_hours, created_at, eta, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no, customer, priority, order_status, 24,
            now.strftime("%Y-%m-%d %H:%M:%S"), eta.strftime("%Y-%m-%d %H:%M:%S"), notes
        ))
        order_id = cursor.lastrowid

        for item in valid_items:
            conn.execute("""
                INSERT INTO order_items (order_id, product_id, requested, allocated)
                VALUES (?, ?, ?, ?)
            """, (order_id, item["product_id"], item["requested"], item["allocated"]))

            if item["allocated"] > 0:
                conn.execute("""
                    UPDATE products
                    SET reserved = reserved + ?
                    WHERE id = ?
                """, (item["allocated"], item["product_id"]))

            if item["allocated"] < item["requested"]:
                shortage = item["requested"] - item["allocated"]
                conn.execute("""
                    INSERT INTO exceptions
                    (order_id, product_id, type, severity, description, decision, resolution, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    item["product_id"],
                    "Out of Stock Shortage",
                    "Critical" if priority in ["Urgent", "High"] else "Warning",
                    f"Shortage of {shortage} units for {item['name']} in {order_no}.",
                    "Partial stock allocated. Flagged for Smart Reallocation & Reorder.",
                    "Order set to Stockout status pending inventory replenishment.",
                    "Open",
                    now.strftime("%Y-%m-%d %H:%M:%S")
                ))

        conn.commit()
        conn.close()

        if has_stockout:
            flash(f"Order {order_no} created with Partial Stock Allocation. Out-of-Stock Exception logged!", "warning")
        else:
            flash(f"Order {order_no} created successfully!", "success")

        return redirect(url_for("order_detail", order_id=order_id))

    # --------------------------------------------------------
    # SHOW NEW ORDER PAGE WITH PRODUCTS
    # --------------------------------------------------------

    conn.close()

    return render_template(
        "new_order.html",
        products=products
    )


# ============================================================
# ORDER DETAILS
# ============================================================

@app.route("/order/<int:order_id>")
def order_detail(order_id):

    conn = get_db()

    order = conn.execute("""
        SELECT *
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()

    if order is None:

        conn.close()

        flash(
            "Order not found.",
            "danger"
        )

        return redirect(
            url_for("orders")
        )

    items = conn.execute("""
        SELECT
            order_items.*,
            products.sku,
            products.name,
            products.category,
            products.location,
            products.unit_cost
        FROM order_items
        JOIN products
            ON products.id = order_items.product_id
        WHERE order_items.order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    return render_template(
        "order_detail.html",
        order=order,
        items=items
    )


# ============================================================
# INVENTORY
# ============================================================

@app.route("/inventory")
def inventory():

    conn = get_db()

    products = conn.execute("""
        SELECT *, (stock - reserved) AS available
        FROM products
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "inventory.html",
        products=products
    )


# ============================================================
# PICKING
# ============================================================

@app.route("/picking")
def picking():

    conn = get_db()

    picking_orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE status IN (
            'Pending',
            'Picking',
            'Processing'
        )
        ORDER BY
            CASE priority
                WHEN 'Urgent' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                ELSE 4
            END,
            id ASC
    """).fetchall()

    conn.close()

    return render_template(
        "picking.html",
        orders=picking_orders
    )


@app.route(
    "/picking/update/<int:order_id>",
    methods=["POST"]
)
def update_picking(order_id):

    status = request.form.get("status", "Picking")
    if status not in ["Picking", "Packed"]:
        status = "Picking"

    conn = get_db()

    conn.execute("""
        UPDATE orders
        SET status = ?
        WHERE id = ?
    """, (status, order_id))

    conn.commit()
    conn.close()

    flash(
        f"Order status updated to {status}.",
        "success"
    )

    return redirect(
        url_for("picking")
    )


# ============================================================
# DISPATCH
# ============================================================

@app.route("/dispatch")
def dispatch():

    conn = get_db()

    dispatch_orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE status IN (
            'Packed',
            'Ready',
            'Dispatched'
        )
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "dispatch.html",
        dispatched_orders=dispatch_orders
    )


@app.route(
    "/dispatch/<int:order_id>",
    methods=["POST"]
)
def update_dispatch(order_id):

    conn = get_db()

    # Get order current status before dispatching
    order = conn.execute("""
        SELECT status FROM orders WHERE id = ?
    """, (order_id,)).fetchone()

    if order and order["status"] != "Dispatched":
        # Deduct requested quantities from actual stock & reserved stock
        items = conn.execute("""
            SELECT product_id, requested
            FROM order_items
            WHERE order_id = ?
        """, (order_id,)).fetchall()

        for item in items:
            conn.execute("""
                UPDATE products
                SET stock = MAX(0, stock - ?),
                    reserved = MAX(0, reserved - ?)
                WHERE id = ?
            """, (item["requested"], item["requested"], item["product_id"]))

    conn.execute("""
        UPDATE orders
        SET status = 'Dispatched'
        WHERE id = ?
    """, (order_id,))

    conn.commit()
    conn.close()

    flash(
        "Order dispatched successfully and stock updated.",
        "success"
    )

    return redirect(
        url_for("dispatch")
    )


# ============================================================
# ANALYTICS
# ============================================================

@app.route("/analytics")
def analytics():

    conn = get_db()

    status_data = conn.execute("""
        SELECT status, COUNT(*) AS count
        FROM orders
        GROUP BY status
    """).fetchall()

    category_data = conn.execute("""
        SELECT category, COUNT(*) AS count
        FROM products
        GROUP BY category
    """).fetchall()

    inventory_value = conn.execute("""
        SELECT COALESCE(
            SUM(stock * unit_cost),
            0
        )
        FROM products
    """).fetchone()[0]

    conn.close()

    return render_template(
        "analytics.html",
        status_data=status_data,
        category_data=category_data,
        inventory_value=inventory_value
    )


# ============================================================
# ALERTS
# ============================================================

@app.route("/alerts")
def alerts():

    conn = get_db()

    low_stock_products = conn.execute("""
        SELECT *
        FROM products
        WHERE stock <= reorder_level
        ORDER BY stock ASC
    """).fetchall()

    open_exceptions = conn.execute("""
        SELECT *
        FROM exceptions
        WHERE status = 'Open'
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "alerts.html",
        low_stock_products=low_stock_products,
        exceptions=open_exceptions
    )


# ============================================================
# QUALITY CHECK (QC)
# ============================================================

@app.route("/qc")
def qc():
    conn = get_db()

    qc_orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE status IN ('Packed', 'QC Pending', 'QC Failed')
        ORDER BY
            CASE priority
                WHEN 'Urgent' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                ELSE 4
            END,
            id ASC
    """).fetchall()

    orders_with_items = []
    for order in qc_orders:
        items = conn.execute("""
            SELECT oi.*, p.name, p.sku, p.location, p.stock, (p.stock - p.reserved) AS available
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
        """, (order["id"],)).fetchall()
        orders_with_items.append({
            "order": order,
            "items": items
        })

    conn.close()

    return render_template(
        "qc.html",
        orders=qc_orders,
        orders_with_items=orders_with_items
    )


@app.route("/qc/update/<int:order_id>", methods=["POST"])
def update_qc(order_id):
    result = request.form.get("result", "Passed")
    notes = request.form.get("notes", "").strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()

    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("qc"))

    if result == "Passed":
        conn.execute("""
            UPDATE orders
            SET status = 'Ready',
                qc_status = 'Passed',
                qc_at = ?
            WHERE id = ?
        """, (now, order_id))

        flash(f"{order['order_no']} passed Quality Check! Ready for dispatch.", "success")

    else:
        conn.execute("""
            UPDATE orders
            SET status = 'QC Failed',
                qc_status = 'Failed',
                qc_at = ?
            WHERE id = ?
        """, (now, order_id))

        conn.execute("""
            INSERT INTO exceptions
            (order_id, type, severity, description, decision, resolution, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            "Quality Check Defect",
            "High",
            f"QC Inspection failed for {order['order_no']}. {notes or 'Item damaged or missing barcode.'}",
            "Quarantine item and trigger stock replacement inspection.",
            "Order set to QC Failed. Warehouse team notified for replacement pick.",
            "Open",
            now
        ))

        flash(f"{order['order_no']} failed Quality Check. Exception logged for inspection.", "warning")

    conn.commit()
    conn.close()

    return redirect(url_for("qc"))


# ============================================================
# DEFECT ACTION RESOLUTION ENGINE
# ============================================================

@app.route("/qc/resolve-replacement/<int:order_id>", methods=["POST"])
def qc_resolve_replacement(order_id):
    conn = get_db()

    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("qc"))

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in items:
        conn.execute("""
            UPDATE products
            SET damaged = damaged + 1,
                stock = MAX(0, stock - 1)
            WHERE id = ?
        """, (item["product_id"],))

    conn.execute("""
        UPDATE orders
        SET status = 'Picking',
            qc_status = 'Pending'
        WHERE id = ?
    """, (order_id,))

    conn.execute("""
        UPDATE exceptions
        SET status = 'Resolved',
            resolution = 'Defect Action Executed: Damaged unit quarantined. Replacement pick ticket generated.'
        WHERE order_id = ? AND type = 'Quality Check Defect'
    """, (order_id,))

    conn.commit()
    conn.close()

    flash(f"Defect Action Executed: Damaged unit quarantined & {order['order_no']} moved to Picking for replacement pick!", "success")
    return redirect(url_for("qc"))


@app.route("/qc/resolve-partial-dispatch/<int:order_id>", methods=["POST"])
def qc_resolve_partial_dispatch(order_id):
    conn = get_db()

    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("qc"))

    conn.execute("""
        UPDATE orders
        SET status = 'Ready',
            qc_status = 'Partial Passed'
        WHERE id = ?
    """, (order_id,))

    conn.execute("""
        UPDATE exceptions
        SET status = 'Resolved',
            resolution = 'Defect Action Executed: Approved Partial Dispatch for intact items. Defective item backordered.'
        WHERE order_id = ? AND type = 'Quality Check Defect'
    """, (order_id,))

    conn.commit()
    conn.close()

    flash(f"Defect Action Executed: Partial Dispatch approved for {order['order_no']}. Ready for shipment!", "success")
    return redirect(url_for("qc"))


@app.route("/qc/resolve-cancel/<int:order_id>", methods=["POST"])
def qc_resolve_cancel(order_id):
    conn = get_db()

    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("qc"))

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in items:
        if item["allocated"] > 0:
            conn.execute("""
                UPDATE products
                SET reserved = MAX(0, reserved - ?)
                WHERE id = ?
            """, (item["allocated"], item["product_id"]))

    conn.execute("""
        UPDATE orders
        SET status = 'Cancelled',
            qc_status = 'Cancelled'
        WHERE id = ?
    """, (order_id,))

    conn.execute("""
        UPDATE exceptions
        SET status = 'Resolved',
            resolution = 'Defect Action Executed: Order cancelled due to unresolvable defect. Allocated stock released.'
        WHERE order_id = ? AND type = 'Quality Check Defect'
    """, (order_id,))

    conn.commit()
    conn.close()

    flash(f"Defect Action Executed: {order['order_no']} cancelled and reserved stock released to inventory.", "warning")
    return redirect(url_for("qc"))


# ============================================================
# SMART DECISION ENGINE: STOCK REALLOCATION & OPTIMIZATION
# ============================================================

@app.route("/orders/reallocate/<int:order_id>", methods=["POST"])
def smart_reallocate(order_id):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    target_order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not target_order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("orders"))

    target_items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    reallocated_count = 0

    for item in target_items:
        prod = conn.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
        needed = item["requested"] - item["allocated"]

        if needed > 0 and prod:
            available = prod["stock"] - prod["reserved"]
            if available < needed:
                shortage = needed - available
                other_items = conn.execute("""
                    SELECT oi.*, o.order_no, o.priority
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    WHERE oi.product_id = ? AND o.id != ? AND o.status = 'Pending' AND oi.allocated > 0
                    ORDER BY CASE o.priority WHEN 'Low' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
                """, (item["product_id"], order_id)).fetchall()

                transferred = 0
                for o_item in other_items:
                    take = min(shortage - transferred, o_item["allocated"])
                    if take > 0:
                        conn.execute("UPDATE order_items SET allocated = allocated - ? WHERE id = ?", (take, o_item["id"]))
                        conn.execute("UPDATE order_items SET allocated = allocated + ? WHERE id = ?", (take, item["id"]))
                        transferred += take

                        conn.execute("""
                            INSERT INTO exceptions
                            (order_id, product_id, type, severity, description, decision, resolution, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            o_item["order_id"],
                            item["product_id"],
                            "Smart Reallocation",
                            "Warning",
                            f"Reallocated {take} units of {prod['name']} from {o_item['order_no']} to higher priority {target_order['order_no']}.",
                            "Priority Preemption Engine invoked.",
                            f"Order {o_item['order_no']} pending stock replenishment.",
                            "Open",
                            now
                        ))

                if transferred > 0:
                    reallocated_count += transferred

    conn.commit()
    conn.close()

    if reallocated_count > 0:
        flash(f"Smart Decision Engine successfully reallocated {reallocated_count} stock units to {target_order['order_no']}!", "success")
    else:
        flash("No lower-priority reserved stock available for reallocation.", "warning")

    return redirect(url_for("order_detail", order_id=order_id))


# ============================================================
# SMART INVENTORY REORDER API
# ============================================================

@app.route("/inventory/reorder/<int:product_id>", methods=["POST"])
def reorder_product(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("inventory"))

    reorder_qty = product["reorder_qty"] or 25
    conn.execute("""
        UPDATE products
        SET stock = stock + ?
        WHERE id = ?
    """, (reorder_qty, product_id))

    conn.commit()
    conn.close()

    flash(f"Generated Purchase Order & restocked {reorder_qty} units of {product['name']}.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/restock-all", methods=["POST"])
def restock_all_out_of_stock():
    conn = get_db()
    low_products = conn.execute("""
        SELECT * FROM products WHERE stock <= reorder_level OR (stock - reserved) <= 0
    """).fetchall()

    count = 0
    for p in low_products:
        qty = p["reorder_qty"] or 25
        conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (qty, p["id"]))
        count += 1

    conn.commit()
    conn.close()

    flash(f"Emergency Purchase Orders generated! Restocked {count} low/out-of-stock products.", "success")
    return redirect(url_for("inventory"))


# ============================================================
# PICKING ROUTE OPTIMIZER API
# ============================================================

@app.route("/api/picking-route/<int:order_id>")
def picking_route_api(order_id):
    conn = get_db()

    items = conn.execute("""
        SELECT oi.*, p.name, p.sku, p.location, p.category
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY p.location ASC
    """, (order_id,)).fetchall()

    conn.close()

    route = []
    for step, item in enumerate(items, 1):
        route.append({
            "step": step,
            "product_name": item["name"],
            "sku": item["sku"],
            "location": item["location"],
            "requested": item["requested"]
        })

    return jsonify({"order_id": order_id, "optimized_route": route})


# ============================================================
# DASHBOARD API
# ============================================================

@app.route("/api/dashboard")
def dashboard_api():

    conn = get_db()

    data = {

        "products": conn.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0],

        "orders": conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0],

        "pending": conn.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'Pending'
        """).fetchone()[0],

        "picking": conn.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'Picking'
        """).fetchone()[0],

        "dispatched": conn.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'Dispatched'
        """).fetchone()[0],

        "low_stock": conn.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE stock <= reorder_level
        """).fetchone()[0]
    }

    conn.close()

    return jsonify(data)


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <h1>404 - Page Not Found</h1>
    <p>The requested page does not exist.</p>
    <a href="/">Go to Dashboard</a>
    """, 404


@app.errorhandler(500)
def internal_error(error):

    return """
    <h1>500 - Internal Server Error</h1>
    <p>Please check the Flask terminal for the error.</p>
    <a href="/">Go to Dashboard</a>
    """, 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    # IMPORTANT:
    # Database initialization must happen BEFORE Flask starts.

    init_db()

    print("=" * 60)
    print("SMART WAREHOUSE OPERATIONS SYSTEM")
    print("=" * 60)
    print("Database:", DB_PATH)
    print("Server:   http://127.0.0.1:5000")
    print("Dashboard: http://127.0.0.1:5000/")
    print("=" * 60)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
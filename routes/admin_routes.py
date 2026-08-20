import os
import functools
from flask import (Blueprint, render_template_string, request,
                   redirect, url_for, session, jsonify, current_app)
from core.links_store import (get_all_links, get_product_links,
                               set_product_links, delete_product_links,
                               get_stats)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ── Credentials (change these!) ───────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "appliance123")
SECRET_KEY     = os.getenv("SECRET_KEY",     "change-this-secret-key-xyz")


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── Login ─────────────────────────────────────────────
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        error = "Invalid username or password."
    return render_template_string(LOGIN_HTML, error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ── Dashboard ─────────────────────────────────────────
@admin_bp.route("/")
@login_required
def dashboard():
    products   = current_app.products
    links      = get_all_links()
    stats      = get_stats()
    total      = len(products)
    unlinked   = total - stats["total_linked"]
    return render_template_string(
        DASHBOARD_HTML,
        products=products,
        links=links,
        stats=stats,
        total=total,
        unlinked=unlinked,
    )


# ── API: get links for one product ────────────────────
@admin_bp.route("/api/links/<product_id>", methods=["GET"])
@login_required
def get_links(product_id):
    return jsonify(get_product_links(product_id))


# ── API: save links for one product ──────────────────
@admin_bp.route("/api/links/<product_id>", methods=["POST"])
@login_required
def save_links(product_id):
    data = request.get_json(silent=True) or {}
    entry = set_product_links(
        product_id,
        daraz=data.get("daraz", ""),
        amazon=data.get("amazon", ""),
        custom=data.get("custom", ""),
        custom_label=data.get("custom_label", ""),
    )
    return jsonify({"ok": True, "links": entry})


# ── API: delete links for one product ─────────────────
@admin_bp.route("/api/links/<product_id>", methods=["DELETE"])
@login_required
def remove_links(product_id):
    delete_product_links(product_id)
    return jsonify({"ok": True})


# ── Public API: get links (for frontend cards) ────────
@admin_bp.route("/api/public/links", methods=["GET"])
def public_links():
    """Returns all links — used by main.js to show Buy buttons."""
    return jsonify(get_all_links())


# ══════════════════════════════════════════════════════
#  HTML TEMPLATES (inline for single-file simplicity)
# ══════════════════════════════════════════════════════

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="light">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Admin Login · ApplianceSearch</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet"/>
  <style>
    body { background: var(--bs-body-secondary-bg); }
    .login-card { max-width: 400px; margin: 100px auto; }
    .brand-icon { font-size: 2.5rem; color: var(--bs-primary); }
  </style>
</head>
<body>
<div class="login-card">
  <div class="card border shadow-sm">
    <div class="card-body p-4">
      <div class="text-center mb-4">
        <i class="bi bi-shield-lock-fill brand-icon"></i>
        <h4 class="fw-semibold mt-2 mb-0">Admin Panel</h4>
        <p class="text-body-secondary small">ApplianceSearch</p>
      </div>
      {% if error %}
      <div class="alert alert-danger py-2 small">
        <i class="bi bi-exclamation-circle me-1"></i>{{ error }}
      </div>
      {% endif %}
      <form method="POST">
        <div class="mb-3">
          <label class="form-label small fw-semibold">Username</label>
          <div class="input-group">
            <span class="input-group-text"><i class="bi bi-person"></i></span>
            <input type="text" name="username" class="form-control" placeholder="admin" required autofocus/>
          </div>
        </div>
        <div class="mb-4">
          <label class="form-label small fw-semibold">Password</label>
          <div class="input-group">
            <span class="input-group-text"><i class="bi bi-lock"></i></span>
            <input type="password" name="password" class="form-control" placeholder="••••••••" required/>
          </div>
        </div>
        <button type="submit" class="btn btn-primary w-100 fw-semibold">
          <i class="bi bi-box-arrow-in-right me-2"></i>Sign In
        </button>
      </form>
    </div>
  </div>
  <p class="text-center text-body-secondary small mt-3">
    <a href="/" class="text-decoration-none"><i class="bi bi-arrow-left me-1"></i>Back to search</a>
  </p>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="light">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Admin Dashboard · ApplianceSearch</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet"/>
  <style>
    body { background: var(--bs-body-secondary-bg); font-size: 14px; }
    .sidebar { width: 220px; min-height: 100vh; background: var(--bs-body-bg); border-right: 1px solid var(--bs-border-color); position: fixed; top: 0; left: 0; padding: 24px 16px; }
    .main-content { margin-left: 220px; padding: 24px; }
    .stat-card { background: var(--bs-body-bg); border: 1px solid var(--bs-border-color); border-radius: 10px; padding: 16px 20px; }
    .stat-num { font-size: 1.8rem; font-weight: 600; }
    .product-row:hover { background: var(--bs-primary-bg-subtle); }
    .link-badge { font-size: 11px; padding: 2px 8px; border-radius: 20px; }
    .has-link { background: var(--bs-success-bg-subtle); color: var(--bs-success-text-emphasis); border: 1px solid rgba(var(--bs-success-rgb),.2); }
    .no-link  { background: var(--bs-secondary-bg); color: var(--bs-secondary-color); border: 1px solid var(--bs-border-color); }
    .shop-icon { font-size: 16px; }
    .table th { font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--bs-secondary-color); font-weight: 600; }
    #searchBox { max-width: 320px; }
    .modal-body label { font-size: 12px; font-weight: 600; color: var(--bs-secondary-color); text-transform: uppercase; letter-spacing: .3px; }
    .brand-logo { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
    .logo-daraz  { background: #f85606; color: #fff; }
    .logo-amazon { background: #ff9900; color: #000; }
    .logo-custom { background: var(--bs-primary); color: #fff; }
    .nav-link { color: var(--bs-body-color); border-radius: 8px; margin-bottom: 2px; font-size: 13px; }
    .nav-link:hover, .nav-link.active { background: var(--bs-primary-bg-subtle); color: var(--bs-primary); }
    .nav-link i { width: 20px; }
  </style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
  <div class="d-flex align-items-center gap-2 mb-4 px-2">
    <i class="bi bi-house-heart-fill text-primary fs-5"></i>
    <span class="fw-semibold">ApplianceSearch</span>
  </div>
  <div class="text-uppercase small fw-semibold text-body-secondary px-2 mb-2" style="font-size:10px;letter-spacing:.5px">Menu</div>
  <a href="/admin/" class="nav-link active d-flex align-items-center gap-2 px-2 py-2">
    <i class="bi bi-grid-1x2"></i>Dashboard
  </a>
  <a href="/" target="_blank" class="nav-link d-flex align-items-center gap-2 px-2 py-2">
    <i class="bi bi-search"></i>View Search
  </a>
  <hr class="my-3"/>
  <a href="/admin/logout" class="nav-link d-flex align-items-center gap-2 px-2 py-2 text-danger">
    <i class="bi bi-box-arrow-right"></i>Logout
  </a>
</div>

<!-- Main content -->
<div class="main-content">

  <!-- Header -->
  <div class="d-flex justify-content-between align-items-center mb-4">
    <div>
      <h4 class="fw-semibold mb-0">Shop Links</h4>
      <p class="text-body-secondary small mb-0">Manage Daraz, Amazon and custom buy links per product</p>
    </div>
    <div class="d-flex gap-2">
      <button class="btn btn-sm btn-outline-secondary" onclick="toggleTheme()">
        <i class="bi bi-moon-fill" id="themeIcon"></i>
      </button>
    </div>
  </div>

  <!-- Stat cards -->
  <div class="row g-3 mb-4">
    <div class="col-sm-3">
      <div class="stat-card">
        <div class="text-body-secondary small mb-1"><i class="bi bi-box-seam me-1"></i>Total Products</div>
        <div class="stat-num">{{ total }}</div>
      </div>
    </div>
    <div class="col-sm-3">
      <div class="stat-card">
        <div class="text-body-secondary small mb-1"><i class="bi bi-link-45deg me-1 text-success"></i>Linked</div>
        <div class="stat-num text-success">{{ stats.total_linked }}</div>
      </div>
    </div>
    <div class="col-sm-3">
      <div class="stat-card">
        <div class="text-body-secondary small mb-1"><i class="bi bi-dash-circle me-1 text-warning"></i>Unlinked</div>
        <div class="stat-num text-warning">{{ unlinked }}</div>
      </div>
    </div>
    <div class="col-sm-3">
      <div class="stat-card">
        <div class="text-body-secondary small mb-1"><i class="bi bi-shop me-1 text-primary"></i>Daraz / Amazon</div>
        <div class="stat-num text-primary">{{ stats.daraz_count }} / {{ stats.amazon_count }}</div>
      </div>
    </div>
  </div>

  <!-- Search + filter -->
  <div class="card border mb-3">
    <div class="card-body p-3 d-flex gap-3 align-items-center flex-wrap">
      <input type="text" id="searchBox" class="form-control form-control-sm"
             placeholder="Search product name or brand…" oninput="filterTable()"/>
      <select class="form-select form-select-sm" style="max-width:160px" id="linkFilter" onchange="filterTable()">
        <option value="all">All products</option>
        <option value="linked">Linked only</option>
        <option value="unlinked">Unlinked only</option>
      </select>
      <span class="text-body-secondary small ms-auto" id="rowCount"></span>
    </div>
  </div>

  <!-- Products table -->
  <div class="card border">
    <div class="table-responsive">
      <table class="table table-hover mb-0" id="productsTable">
        <thead class="table-light border-bottom">
          <tr>
            <th>Product</th>
            <th>Brand</th>
            <th>Category</th>
            <th>Price (PKR)</th>
            <th>Daraz</th>
            <th>Amazon</th>
            <th>Custom</th>
            <th class="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for p in products %}
          {% set pid = p.get('product_id','') %}
          {% set lnk = links.get(pid, {}) %}
          <tr class="product-row" data-pid="{{ pid }}"
              data-name="{{ p.get('product_name','') | lower }}"
              data-brand="{{ p.get('brand','') | lower }}"
              data-linked="{{ 'yes' if lnk else 'no' }}">
            <td>
              <div class="fw-semibold" style="font-size:13px">{{ p.get('product_name','') }}</div>
              <div class="text-body-secondary" style="font-size:11px">{{ pid }}</div>
            </td>
            <td>{{ p.get('brand','') }}</td>
            <td><span class="badge bg-primary-subtle text-primary-emphasis border" style="font-size:10px">{{ p.get('category','') }}</span></td>
            <td>{{ '{:,}'.format(p.get('price_pkr', 0) | int) }}</td>
            <td>
              {% if lnk.get('daraz') %}
              <span class="brand-logo logo-daraz">D</span>
              {% else %}<span class="text-body-tertiary">—</span>{% endif %}
            </td>
            <td>
              {% if lnk.get('amazon') %}
              <span class="brand-logo logo-amazon">A</span>
              {% else %}<span class="text-body-tertiary">—</span>{% endif %}
            </td>
            <td>
              {% if lnk.get('custom') %}
              <span class="brand-logo logo-custom"><i class="bi bi-link-45deg"></i></span>
              {% else %}<span class="text-body-tertiary">—</span>{% endif %}
            </td>
            <td class="text-end">
              <button class="btn btn-sm btn-outline-primary" onclick="openEdit('{{ pid }}','{{ p.get(\"product_name\",\"\") }}')">
                <i class="bi bi-pencil me-1"></i>Edit Links
              </button>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div><!-- /main -->

<!-- Edit Links Modal -->
<div class="modal fade" id="editModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header border-bottom">
        <h5 class="modal-title fw-semibold" id="editModalTitle">Edit Links</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body p-4">
        <input type="hidden" id="editPid"/>
        <div class="mb-3">
          <label><span class="brand-logo logo-daraz me-2">D</span>Daraz URL</label>
          <input type="url" id="editDaraz" class="form-control mt-1" placeholder="https://www.daraz.pk/products/…"/>
        </div>
        <div class="mb-3">
          <label><span class="brand-logo logo-amazon me-2">A</span>Amazon URL</label>
          <input type="url" id="editAmazon" class="form-control mt-1" placeholder="https://www.amazon.com/dp/…"/>
        </div>
        <div class="mb-3">
          <label><span class="brand-logo logo-custom me-2"><i class="bi bi-link-45deg"></i></span>Custom URL</label>
          <input type="url" id="editCustom" class="form-control mt-1" placeholder="https://yourshop.com/product/…"/>
        </div>
        <div class="mb-0">
          <label>Custom Button Label</label>
          <input type="text" id="editCustomLabel" class="form-control mt-1" placeholder="e.g. Buy on OLX"/>
        </div>
      </div>
      <div class="modal-footer border-top gap-2">
        <button class="btn btn-sm btn-outline-danger me-auto" onclick="deleteLinks()">
          <i class="bi bi-trash me-1"></i>Remove all links
        </button>
        <button class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Cancel</button>
        <button class="btn btn-sm btn-primary" onclick="saveLinks()">
          <i class="bi bi-check-lg me-1"></i>Save Links
        </button>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
const editModal = new bootstrap.Modal(document.getElementById('editModal'));

function openEdit(pid, name) {
  document.getElementById('editPid').value = pid;
  document.getElementById('editModalTitle').textContent = 'Edit Links — ' + name;
  document.getElementById('editDaraz').value = '';
  document.getElementById('editAmazon').value = '';
  document.getElementById('editCustom').value = '';
  document.getElementById('editCustomLabel').value = '';

  fetch('/admin/api/links/' + pid)
    .then(r => r.json())
    .then(d => {
      document.getElementById('editDaraz').value       = d.daraz        || '';
      document.getElementById('editAmazon').value      = d.amazon       || '';
      document.getElementById('editCustom').value      = d.custom       || '';
      document.getElementById('editCustomLabel').value = d.custom_label || '';
    });
  editModal.show();
}

function saveLinks() {
  const pid = document.getElementById('editPid').value;
  const body = {
    daraz:        document.getElementById('editDaraz').value.trim(),
    amazon:       document.getElementById('editAmazon').value.trim(),
    custom:       document.getElementById('editCustom').value.trim(),
    custom_label: document.getElementById('editCustomLabel').value.trim(),
  };
  fetch('/admin/api/links/' + pid, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body),
  })
  .then(r => r.json())
  .then(() => { editModal.hide(); location.reload(); });
}

function deleteLinks() {
  const pid = document.getElementById('editPid').value;
  if (!confirm('Remove all links for this product?')) return;
  fetch('/admin/api/links/' + pid, { method: 'DELETE' })
    .then(() => { editModal.hide(); location.reload(); });
}

function filterTable() {
  const q      = document.getElementById('searchBox').value.toLowerCase();
  const filter = document.getElementById('linkFilter').value;
  const rows   = document.querySelectorAll('#productsTable tbody tr');
  let   visible = 0;
  rows.forEach(row => {
    const name    = row.dataset.name    || '';
    const brand   = row.dataset.brand   || '';
    const linked  = row.dataset.linked  || 'no';
    const matchQ  = !q || name.includes(q) || brand.includes(q);
    const matchF  = filter === 'all' ||
                    (filter === 'linked'   && linked === 'yes') ||
                    (filter === 'unlinked' && linked === 'no');
    const show = matchQ && matchF;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  document.getElementById('rowCount').textContent = visible + ' products';
}

function toggleTheme() {
  const html = document.documentElement;
  const dark  = html.getAttribute('data-bs-theme') === 'dark';
  html.setAttribute('data-bs-theme', dark ? 'light' : 'dark');
  document.getElementById('themeIcon').className = dark ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
}

// Init row count
filterTable();
</script>
</body>
</html>
"""



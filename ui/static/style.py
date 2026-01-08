from nicegui import ui

BRAND_BLUE = '#2e4a74'
ACCENT = '#20b389'
BG = '#f6f7fb'
CARD_BG = '#ffffff'
BORDER = '#e8edf3'


def change_colors():
    ui.colors(primary=BRAND_BLUE, secondary=ACCENT, accent=ACCENT)


def add_style():
    ui.add_head_html("""
        <link href="https://fonts.googleapis.com/css?family=Montserrat:700,400&display=swap" rel="stylesheet">
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <style>
        html, body {
        width: 100%;
        min-height: 100vh;
        overflow-x: hidden;
        box-sizing: border-box;
        font-family: 'Montserrat', Arial, sans-serif;
        background: #f8fafd;
        color: #222;
        margin: 0;
        }
        body {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        margin: 0;
        }
        *, *::before, *::after {
            box-sizing: inherit;
        }
        .navbar {
        width: 100%;
        left: 0;
        position: relative;
        background: #2d4c7c;
        color: #fff;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 20px 40px;
        box-sizing: border-box;
        }
        .nav-left, .nav-right{
        display:flex; align-items:center; gap:2px;
        }
        .navbar a {
        color: #fff;
        text-decoration: none;
        margin-left: 32px;
        font-weight: 500;
        font-size: 1.1em;
        transition: color .2s;
        }
        .navbar a:hover {
        color: #43e97b;
        }
        .settings-menu { 
        background: #2d4c7c !important;
        color: #fff !important;
        border-radius: 10px;
        box-shadow: 0 8px 24px rgba(0,0,0,.25);
        }

        /* Quasar listy i itemy wewnątrz menu */
        .settings-menu .q-list,
        .settings-menu .q-item {
        background: #2d4c7c !important;
        color: #fff !important;
        padding: 5px 30px !important;
        }
        .settings-menu .q-item__section, 
        .settings-menu .q-item__label, 
        .settings-menu .q-icon {
        color: #fff !important;
        }

        /* hover = zielony jak w navbarze */
        .settings-menu .q-item.q-hoverable:hover .q-item__label,
        .settings-menu .q-item.q-hoverable:focus .q-item__label {
        color: #43e97b !important;
        }

        /* separator jaśniejszy */
        .settings-menu .q-separator {
        background: rgba(255,255,255,.25) !important;
        }
        .hero {
        position: relative;
        width: 100%;
        height: 400px;
        background-image: url('https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1200&q=80');
        background-size: cover;
        background-position: center;
        display: flex;
        align-items: center;
        justify-content: center;
        }
        .hero-content {
        background: rgba(255,255,255,0.88);
        padding: 40px 60px;
        border-radius: 24px;
        box-shadow: 0 6px 24px rgba(44,76,124,0.07);
        text-align: center;
        }
        .hero-content h1 {
        margin: 0 0 12px 0;
        color: #008080;
        font-size: 2.7em;
        font-weight: bold;
        }
        .hero-content p {
        font-size: 1.15em;
        margin-bottom: 24px;
        color: #444;
        }
        .hero-content .cta-buttons {
        margin-top: 18px;
        }
        .cta-btn {
        display: inline-block;
        padding: 15px 36px;
        font-size: 1.1em;
        border: none;
        border-radius: 6px;
        margin: 0 12px;
        background: #00bfae;
        color: #fff;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s;
        text-decoration: none;
        }
        .cta-btn.alt {
        background: #43e97b;
        color: #fff;
        }
        .cta-btn:hover {
        background: #2d4c7c;
        color: #fff;
        }
        .features {
        display: flex;
        width: 100%;
        justify-content: center;
        gap: 48px;
        margin: 50px 0 30px 0;
        flex-wrap: wrap;
        box-sizing: border-box;
        }
        .feature-box {
        background: #fff;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(44,76,124,0.06);
        padding: 28px 36px;
        text-align: center;
        width: 260px;
        margin-bottom: 24px;
        }
        .feature-box img {
        width: 48px;
        margin-bottom: 14px;
        }
        .feature-title {
        font-weight: 600;
        font-size: 1.12em;
        margin-bottom: 7px;
        color: #2d4c7c;
        }
        .feature-desc {
        color: #555;
        font-size: 1em;
        }
        .why-section {
        max-width: 800px;
        margin: 50px auto 60px auto;
        padding: 36px 32px;
        background: #fff;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(44,76,124,0.08);
        text-align: center;
        }
        .why-section h2 {
        color: #008080;
        font-size: 2em;
        margin-bottom: 14px;
        }
        .why-section ul {
        text-align: left;
        display: inline-block;
        margin: 0 auto;
        padding-left: 20px;
        }
        .why-section li {
        font-size: 1.1em;
        margin-bottom: 9px;
        color: #333;
        }
        .main-content {
        flex: 1 0 auto;
        width: 100%;
        display: flex;
        flex-direction: column;
        min-height: 0; 
        }
        .centered-content {
        display: flex;
        justify-content: center;
        align-items: center;
        flex: 1 0 auto;
        width: 100%;
        height: 100%;
        min-height: 100%; 
        }
        .footer {
        width: 100%;
        flex-shrink: 0;
        margin-top: auto;
        left: 0;
        position: relative;
        background: #2d4c7c;
        color: #fff;
        padding: 24px 40px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.98em;
        box-sizing: border-box;
        }
        .user-name-chip{
        padding:6px 12px;
        border:1px solid rgba(255,255,255,.35);
        border-radius:9999px;
        background:rgba(255,255,255,.06);
        color:#fff; font-weight:600; letter-spacing:.2px;
        display:inline-flex; align-items:center; gap:8px;
        transition:all .18s ease; backdrop-filter:saturate(120%) blur(2px);
        }
        .user-name-chip:hover{ border-color:#43e97b; color:#43e97b; box-shadow:0 0 0 1px rgba(67,233,123,.35) inset; }
        .user-name-dot{ width:8px; height:8px; border-radius:50%; background:#43e97b; }
        .user-name{ max-width:160px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
          .wm-wrap { width: min(1600px, 98vw); margin: 0 auto; }
        .wm-card {
        border-radius: 20px;
        background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
        box-shadow: 0 10px 24px rgba(15,23,42,.06);
        border: 1px solid rgba(2,6,23,.06);
        }
        .wm-title { font-size: 20px; font-weight: 600; }
        .wm-sub { font-size: 13px; color: #64748b; }
        .wm-kpi { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
        .wm-pill {
        display:inline-flex; gap:8px; align-items:center;
        padding: 7px 10px; border-radius: 999px;
        border: 1px solid rgba(2,6,23,.08);
        background: rgba(255,255,255,.7);
        font-size: 12px;
        }
        .wm-row {
        display:flex; justify-content:space-between; align-items:center;
        gap:12px; padding: 10px 12px;
        border-radius: 14px;
        border: 1px solid rgba(2,6,23,.06);
        background: rgba(255,255,255,.65);
        }
        .wm-row-title { font-weight: 600; }
        .wm-row-sub { font-size: 12px; color:#64748b; }
        .wm-exp-wrap { width: min(1200px, 80%); margin: 10px auto; }

        .wm-exp-card {
            border-radius: 18px;
            border: 1px solid rgba(2,6,23,.07);
            background: rgba(37,99,235,.03); /* subtle blue tint */
            box-shadow: 0 6px 18px rgba(15,23,42,.05);
        }

        .wm-exp-card .q-expansion-item__container { border-radius: 18px; }

        .wm-exp-card .q-expansion-item__content {
            padding: 12px 12px 10px;
        }

        .wm-inner-card {
            border-radius: 16px;
            border: 1px solid rgba(2,6,23,.06);
            background: rgba(255,255,255,.75);
            box-shadow: 0 6px 14px rgba(15,23,42,.04);
            padding: 12px;
        }

        .wm-subexp-card {
            border-radius: 16px;
            border: 1px solid rgba(2,6,23,.06);
            background: rgba(255,255,255,.55);
            box-shadow: 0 4px 12px rgba(15,23,42,.035);
            padding: 8px 10px;
        }
        .wm-side-stretch{
            align-self: stretch !important;
            display: flex;
        }

        .wm-right{
            height: 90%;
            align-items: stretch;
        }

        .wm-chip-stretch{
            height: 90% !important;
            min-height: 90% !important;
            display: flex !important;
            align-items: center !important;
        }
        .wm-menu{
            min-width: 240px;
            border-radius: 14px;
            box-shadow: 0 14px 40px rgba(15,23,42,.14);
            border: 1px solid rgba(2,6,23,.08);
            overflow: hidden;
        }
        .wm-menu-item{ padding: 10px 12px; }
        .wm-menu-item:hover{ background: rgba(59,130,246,.08); }
        .wm-menu-ic{ opacity: .85; }
        .footer a {
        color: #43e97b;
        text-decoration: none;
        margin-left: 18px;
        }
        @media (max-width: 900px) {
        .features { flex-direction: column; gap: 32px;}
        .feature-box { width: 98%; }
        }
        @media (max-width: 600px) {
        .hero-content { padding: 18px 7vw;}
        .why-section { padding: 15px 2vw;}
        .footer { flex-direction: column; gap: 8px;}
        }
        </style>
        """)


def add_user_style():   
    ui.add_head_html("""
    <style>
        html, body, #app, .q-layout, .q-page, .q-page-container { background:#f2f5fb !important; }
        .toolbar{
            background:#fff !important; border:1px solid #cfd8e3 !important; border-radius:14px !important;
            box-shadow:0 3px 10px rgba(20,30,60,.08), 0 1px 2px rgba(20,30,60,.04) !important;
        }
        .q-card.elevated-card, .card, .q-card--bordered.elevated-card{
            background:#fff !important; border:1px solid #cfd8e3 !important; border-radius:14px !important;
            box-shadow:0 10px 24px rgba(16,24,40,.12), 0 4px 10px rgba(16,24,40,.08) !important;
            transition: box-shadow .2s ease, transform .2s ease;
        }
        .q-card.elevated-card:hover{ 
            box-shadow:0 14px 30px rgba(16,24,40,.16), 0 6px 14px rgba(16,24,40,.10) !important; 
            transform: translateY(-1px); 
        }
        .muted{ color:#6b7280; font-size:12px; }
    
        .q-btn .q-btn__content { gap: 8px; }
        .q-btn { flex: 0 0 auto; }
        .kpi-sub strong{font-weight:600}
        .top4-table thead th{
            background:#fff;
            color:#0f172a;
            font-weight:700;
            border-bottom:1px solid #d7dfeb;
        }
        .top4-table tbody tr:nth-child(odd){ background:#f8fafc; }
        .top4-table tbody tr:hover{ background:#eef5ff; }
        .num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
        .pos { color:#16a34a; }  
        .neg { color:#ef4444; }  
    </style>
    """)
    
    
def add_table_style():
    ui.add_head_html("""
    <style>
        .header-title{
            font-size:24px;
            font-weight:900;
            color: var(--q-primary); /* kolor motywu = spójny z całością */
            margin:0;
            letter-spacing:.2px;
        }
        .balance-pill{
            display:inline-flex;align-items:center;gap:8px;
            padding:8px 12px;border-radius:10px;background:#eef2f7;
            font-weight:800;color:#0f172a;white-space:nowrap;
        }
        .balance-pill .label{
            font-weight:700;
            font-size:12px;
            opacity:.75;
        }
        .balance-pill .amount{
            font-variant-numeric:tabular-nums;
        }
        .balance-pill.pos .amount{color:#16a34a;}  
        .balance-pill.neg .amount{color:#dc2626;} 
        .card-body{ padding:12px 16px 16px 16px; }
        .manage-grid{ display:grid; grid-template-columns: 2fr 1fr; gap:16px; }
        @media (max-width: 1100px){ .manage-grid{ grid-template-columns: 1fr; } }
        .section-col{ display:flex; flex-direction:column; gap:10px; }
        .section-title{ font-size:12px; font-weight:800; letter-spacing:.2px; color:#334155; text-transform:uppercase; }
        .chips-row{ display:flex; flex-wrap:wrap; gap:8px; }
        .q-chip.chip-soft{ background: rgba(15,23,42,.04); border:1px solid rgba(15,23,42,.08); }
        .q-table.table-modern th{ font-weight:700; white-space:nowrap; }
        .q-table.table-modern tbody tr:hover{ background: rgba(67,233,123,.06); }
        .q-table__bottom{ border-top:1px solid rgba(2,6,23,.06); }
        .table-modern { width: 100%; }
        .table-modern .q-table__container { width: 100%; }
        .table-modern .q-table { width: 100%; table-layout: auto; }
        .table-modern td.num { font-variant-numeric: tabular-nums; }
        .table-modern thead tr th {
            position: sticky; top: 0;
            background: #fff;
            z-index: 2;
        }
        .table-modern thead th .q-table__sort-icon {
        font-size: 14px;        /* było ok. 20–24px */
        width: 14px; height: 14px;
        margin-left: 4px;        /* odstęp od tekstu */
        transform: translateY(1px); /* lekkie wyrównanie do linii tekstu */
        opacity: .75;            /* opcjonalnie subtelniejsza ikona */
        }
        .table-modern thead th.sorted .q-table__sort-icon { opacity: 1; }
        .table-modern thead th .q-table__sort-icon svg {
        width: 14px; height: 14px;
        }
        .chip-soft { opacity: .95; }
        .filter-field {
            border-radius: 14px;
            box-shadow: 0 6px 18px rgba(0,0,0,.12);
            transition: box-shadow .18s ease, transform .18s ease;
        }
        .filter-field:hover {
            box-shadow: 0 10px 26px rgba(0,0,0,.16);
        }
        /* gdy pole jest w focusie (Quasar dodaje klasę q-field--focused) */
        .filter-field.q-field--focused .q-field__control {
            box-shadow: 0 14px 34px rgba(0,0,0,.20);
        }

        /* popup z opcjami */
        .filter-popup {
            box-shadow: 0 18px 48px rgba(0,0,0,.25) !important;
            border-radius: 14px;
        }
    </style>
    """)

"""
queries.py — все SQL-запросы для агрегации по date range.
Все функции принимают con, d1, d2 (строки 'YYYY-MM-DD')
и опциональный azs (list[str] | None) для фильтрации по АЗС.
"""
import sqlite3
from typing import Optional

def _where(date_from: str, date_to: str, extra: str = '',
           azs: Optional[list] = None) -> tuple[str, list]:
    """Строит WHERE clause + params."""
    cond = "dt_str >= ? AND dt_str < date(?, '+1 day')"
    params = [date_from + ' 00:00:00', date_to]
    if extra:
        cond += ' AND ' + extra
    if azs:
        placeholders = ','.join('?' * len(azs))
        cond += f' AND azs_num IN ({placeholders})'
        params.extend(azs)
    return cond, params

def fetchall(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

# ─── Overall KPI ─────────────────────────────────────────────────────────────
def q_overall_kpi(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT
          COUNT(DISTINCT receipt_id) AS n_receipts,
          COUNT(*) AS n_lines,
          SUM(gross_amount) AS total_gross,
          SUM(discount) AS total_discount,
          SUM(net_amount) AS total_net
        FROM lines WHERE {w}
    """, p)[0]

def q_by_category(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT category,
          COUNT(DISTINCT receipt_id) AS n_receipts,
          COUNT(*) AS n_lines,
          SUM(gross_amount) AS gross_amount,
          SUM(discount) AS discount,
          SUM(net_amount) AS net_amount
        FROM lines WHERE {w}
        GROUP BY category ORDER BY net_amount DESC
    """, p)

# ─── Топливо ─────────────────────────────────────────────────────────────────
def q_fuel_kpi(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT
          SUM(qty) AS total_qty,
          SUM(net_amount) AS total_net,
          SUM(gross_amount) AS total_gross,
          SUM(discount) AS total_discount,
          COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
    """, p)[0]

def q_fuel_by_product(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT product_name,
          SUM(qty) AS qty, SUM(net_amount) AS net_amount,
          SUM(gross_amount) AS gross_amount, SUM(discount) AS discount,
          COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY product_name ORDER BY qty DESC
    """, p)

def q_fuel_by_day_product(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT substr(dt_str,1,10) AS date_str, product_name,
          SUM(qty) AS qty, SUM(net_amount) AS net_amount,
          COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY date_str, product_name ORDER BY date_str, product_name
    """, p)

def q_fuel_by_azs(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT azs_num,
          SUM(qty) AS qty, SUM(net_amount) AS net_amount,
          COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY azs_num ORDER BY qty DESC
    """, p)

# ─── Оплаты ──────────────────────────────────────────────────────────────────
def q_payments(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT payment_type,
          COUNT(DISTINCT receipt_id) AS n_receipts,
          COUNT(*) AS n_lines,
          SUM(net_amount) AS net_amount,
          SUM(gross_amount) AS gross_amount,
          SUM(discount) AS discount
        FROM lines WHERE {w}
        GROUP BY payment_type ORDER BY net_amount DESC
    """, p)

def q_smartpay_fuel(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel' AND payment_type='SmartPay'", azs=azs)
    return fetchall(con, f"""
        SELECT SUM(qty) AS qty, SUM(net_amount) AS net_amount,
               COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
    """, p)[0]

def q_smartpay_fuel_product(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel' AND payment_type='SmartPay'", azs=azs)
    return fetchall(con, f"""
        SELECT product_name, SUM(qty) AS qty, SUM(net_amount) AS net_amount,
               COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY product_name ORDER BY qty DESC
    """, p)

def q_smartpay_by_hour(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT hour, payment_type,
          SUM(qty) AS qty, COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY hour, payment_type ORDER BY hour
    """, p)

# ─── Лояльность ──────────────────────────────────────────────────────────────
def q_loyalty_kpi(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT has_loyalty,
          COUNT(DISTINCT receipt_id) AS n_receipts,
          SUM(net_amount) AS net_amount,
          SUM(gross_amount) AS gross_amount
        FROM lines WHERE {w}
        GROUP BY has_loyalty
    """, p)

def q_loyalty_fuel(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    return fetchall(con, f"""
        SELECT has_loyalty, product_name,
          SUM(qty) AS qty, SUM(net_amount) AS net_amount,
          COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY has_loyalty, product_name ORDER BY product_name
    """, p)

def q_loyalty_by_azs(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT azs_num, has_loyalty,
          COUNT(DISTINCT receipt_id) AS n_receipts,
          SUM(net_amount) AS net_amount
        FROM lines WHERE {w}
        GROUP BY azs_num, has_loyalty ORDER BY azs_num
    """, p)

def q_arpu(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "has_loyalty=1", azs=azs)
    r = fetchall(con, f"""
        SELECT SUM(net_amount) AS total_net,
               COUNT(DISTINCT loyalty_card_id) AS unique_cards
        FROM lines WHERE {w}
    """, p)[0]
    r['arpu'] = (r['total_net'] or 0) / max(r['unique_cards'] or 1, 1)
    return r

# ─── Смешанные чеки ──────────────────────────────────────────────────────────
def q_receipt_flags(con, d1, d2, azs=None):
    """Возвращает флаги на уровне чека."""
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT receipt_id,
          MAX(CASE WHEN category='fuel'    THEN 1 ELSE 0 END) has_fuel,
          MAX(CASE WHEN category='ff'      THEN 1 ELSE 0 END) has_ff,
          MAX(CASE WHEN category='mm'      THEN 1 ELSE 0 END) has_mm,
          MAX(CASE WHEN category='service' THEN 1 ELSE 0 END) has_service,
          MAX(CASE WHEN category='cert'    THEN 1 ELSE 0 END) has_cert,
          MIN(substr(dt_str,1,10)) AS date_str,
          MIN(azs_num) AS azs_num,
          MIN(payment_type) AS payment_type,
          MAX(has_loyalty) AS has_loyalty,
          SUM(gross_amount) AS total_gross,
          SUM(discount) AS total_discount,
          SUM(net_amount) AS total_net
        FROM lines WHERE {w}
        GROUP BY receipt_id
    """, p)

def q_cross_sell(con, d1, d2, azs=None, _flags=None):
    flags = _flags if _flags is not None else q_receipt_flags(con, d1, d2, azs=azs)
    combos = {}
    for r in flags:
        cats = []
        if r['has_fuel']: cats.append('Топливо')
        if r['has_ff']:   cats.append('ФФ')
        if r['has_mm']:   cats.append('ММ')
        if r['has_service']: cats.append('Услуги')
        if r['has_cert']: cats.append('Серт.')
        label = (' + '.join(cats) if len(cats) > 1 else cats[0] + ' only') if cats else 'Прочее'
        if label not in combos:
            combos[label] = {'combo': label, 'n_receipts': 0, 'total_net': 0.0,
                             'total_gross': 0.0, 'total_discount': 0.0}
        combos[label]['n_receipts'] += 1
        combos[label]['total_net']  += r['total_net'] or 0
        combos[label]['total_gross'] += r['total_gross'] or 0
        combos[label]['total_discount'] += r['total_discount'] or 0

    result = sorted(combos.values(), key=lambda x: -x['total_net'])
    for r in result:
        r['avg_receipt'] = r['total_net'] / max(r['n_receipts'], 1)
    return result

def q_cross_sell_conversion(con, d1, d2, azs=None, _flags=None):
    flags = _flags if _flags is not None else q_receipt_flags(con, d1, d2, azs=azs)
    fuel_only = [r for r in flags if r['has_fuel']]
    total = len(fuel_only)
    if not total:
        return {'total': 0, 'with_ff': 0, 'with_mm': 0, 'with_service': 0,
                'pct_ff': 0, 'pct_mm': 0, 'pct_service': 0}
    with_ff = sum(1 for r in fuel_only if r['has_ff'])
    with_mm = sum(1 for r in fuel_only if r['has_mm'])
    with_svc = sum(1 for r in fuel_only if r['has_service'])
    return {
        'total': total, 'with_ff': with_ff, 'with_mm': with_mm, 'with_service': with_svc,
        'pct_ff': with_ff/total*100, 'pct_mm': with_mm/total*100, 'pct_service': with_svc/total*100,
    }

def q_cross_by_day(con, d1, d2, azs=None, _flags=None):
    flags = _flags if _flags is not None else q_receipt_flags(con, d1, d2, azs=azs)
    by_day = {}
    for r in flags:
        cats = []
        if r['has_fuel']: cats.append('Топливо')
        if r['has_ff']:   cats.append('ФФ')
        if r['has_mm']:   cats.append('ММ')
        if r['has_service']: cats.append('Услуги')
        label = (' + '.join(cats) if len(cats) > 1 else cats[0] + ' only') if cats else 'Прочее'
        key = (r['date_str'], label)
        if key not in by_day:
            by_day[key] = {'date_str': r['date_str'], 'combo': label, 'n_receipts': 0, 'total_net': 0.0}
        by_day[key]['n_receipts'] += 1
        by_day[key]['total_net']  += r['total_net'] or 0
    return sorted(by_day.values(), key=lambda x: (x['date_str'], x['combo']))

def q_azs_cross(con, d1, d2, azs=None, _flags=None):
    flags = _flags if _flags is not None else q_receipt_flags(con, d1, d2, azs=azs)
    azs_data = {}
    for r in flags:
        a = r['azs_num']
        if a not in azs_data:
            azs_data[a] = {'azs_num': a, 'total': 0, 'has_mix': 0, 'total_net': 0.0}
        azs_data[a]['total'] += 1
        azs_data[a]['total_net'] += r['total_net'] or 0
        if r['has_fuel'] and (r['has_ff'] or r['has_mm'] or r['has_service']):
            azs_data[a]['has_mix'] += 1
    result = list(azs_data.values())
    for r in result:
        r['pct_mix'] = r['has_mix'] / max(r['total'], 1) * 100
    return sorted(result, key=lambda x: -x['pct_mix'])

# ─── Скидки ──────────────────────────────────────────────────────────────────
def q_discounts_kpi(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT SUM(discount) AS total_discount, SUM(gross_amount) AS total_gross,
               SUM(net_amount) AS total_net,
               COUNT(DISTINCT CASE WHEN discount>0 THEN receipt_id END) AS n_receipts_with_discount,
               COUNT(DISTINCT receipt_id) AS n_receipts_total
        FROM lines WHERE {w}
    """, p)[0]

def q_discounts_by_category(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT category, SUM(discount) AS discount,
               SUM(net_amount) AS net_amount, COUNT(*) AS n_lines
        FROM lines WHERE {w} GROUP BY category ORDER BY discount DESC
    """, p)

def q_discounts_by_payment(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT payment_type, SUM(discount) AS discount, SUM(net_amount) AS net_amount
        FROM lines WHERE {w} GROUP BY payment_type ORDER BY discount DESC
    """, p)

def q_discounts_by_loyalty(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT has_loyalty, SUM(discount) AS discount,
               SUM(net_amount) AS net_amount, COUNT(*) AS n_lines
        FROM lines WHERE {w} GROUP BY has_loyalty
    """, p)

def q_discounts_by_azs(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT azs_num, SUM(discount) AS discount, SUM(net_amount) AS net_amount,
               COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w} GROUP BY azs_num ORDER BY discount DESC
    """, p)

# ─── ABC ─────────────────────────────────────────────────────────────────────
def q_abc(con, d1, d2, category: str, azs=None):
    w, p = _where(d1, d2, f"category='{category}'", azs=azs)
    rows = fetchall(con, f"""
        SELECT product_name, SUM(qty) AS qty, SUM(net_amount) AS net_amount,
               COUNT(DISTINCT receipt_id) AS n_receipts
        FROM lines WHERE {w}
        GROUP BY product_name ORDER BY net_amount DESC
    """, p)
    total = sum(r['net_amount'] or 0 for r in rows)
    cum = 0.0
    for r in rows:
        pct = (r['net_amount'] or 0) / total * 100 if total else 0
        cum += pct
        r['pct'] = pct
        r['cum_pct'] = cum
        r['abc_group'] = 'A' if cum <= 80 else ('B' if cum <= 95 else 'C')
    return rows

# ─── Heatmap ─────────────────────────────────────────────────────────────────
def q_heatmap_fuel(con, d1, d2, azs=None):
    w, p = _where(d1, d2, "category='fuel'", azs=azs)
    # Normalise by number of unique dates per weekday so weeks with 2 Mondays
    # don't visually outweigh weeks with only 1 Friday.
    return fetchall(con, f"""
        SELECT weekday, hour,
               SUM(qty)                              / COUNT(DISTINCT date(dt_str)) AS qty,
               SUM(net_amount)                       / COUNT(DISTINCT date(dt_str)) AS net_amount,
               COUNT(DISTINCT receipt_id) * 1.0      / COUNT(DISTINCT date(dt_str)) AS n_receipts
        FROM lines WHERE {w} GROUP BY weekday, hour ORDER BY weekday, hour
    """, p)

def q_heatmap_all(con, d1, d2, azs=None):
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT weekday, hour,
               SUM(net_amount)                       / COUNT(DISTINCT date(dt_str)) AS net_amount,
               COUNT(DISTINCT receipt_id) * 1.0      / COUNT(DISTINCT date(dt_str)) AS n_receipts
        FROM lines WHERE {w} GROUP BY weekday, hour ORDER BY weekday, hour
    """, p)

# ─── Combo segment ───────────────────────────────────────────────────────────
def q_combo_segment(con, d1, d2, azs=None, _flags=None):
    flags = _flags if _flags is not None else q_receipt_flags(con, d1, d2, azs=azs)
    segs = {}
    for r in flags:
        is_loy = bool(r['has_loyalty'])
        is_sp  = r['payment_type'] == 'SmartPay'
        if is_loy and is_sp:   seg = 'Лояльность + SmartPay'
        elif is_loy:            seg = 'Лояльность, не SmartPay'
        elif is_sp:             seg = 'SmartPay, без лояльности'
        else:                   seg = 'Прочие'
        if seg not in segs:
            segs[seg] = {'segment': seg, 'n_receipts': 0, 'total_net': 0.0}
        segs[seg]['n_receipts'] += 1
        segs[seg]['total_net']  += r['total_net'] or 0
    result = list(segs.values())
    for r in result:
        r['avg_receipt'] = r['total_net'] / max(r['n_receipts'], 1)
    return result

# ─── Manifest ────────────────────────────────────────────────────────────────
def q_manifest(con):
    return fetchall(con, "SELECT * FROM manifest ORDER BY min_date")

def q_date_range(con):
    """Возвращает min/max дату по всем данным."""
    r = fetchall(con, "SELECT MIN(dt_str) AS min_dt, MAX(dt_str) AS max_dt FROM lines")
    return r[0] if r else {'min_dt': None, 'max_dt': None}

def q_azs_list(con):
    """Возвращает список уникальных номеров АЗС."""
    rows = fetchall(con, "SELECT DISTINCT azs_num FROM lines ORDER BY CAST(azs_num AS INTEGER)")
    return [r['azs_num'] for r in rows]

# ─── Рейтинг АЗС ─────────────────────────────────────────────────────
def q_azs_rating(con, d1, d2, azs=None):
    """Сводный рейтинг по каждой АЗС."""
    w, p = _where(d1, d2, azs=azs)
    rows = fetchall(con, f"""
        SELECT
          azs_num,
          COUNT(DISTINCT receipt_id)                                   AS n_receipts,
          SUM(net_amount)                                              AS net_amount,
          SUM(gross_amount)                                            AS gross_amount,
          SUM(discount)                                                AS discount,
          SUM(CASE WHEN category='fuel' THEN qty      ELSE 0 END)      AS fuel_liters,
          SUM(CASE WHEN category='fuel' THEN net_amount ELSE 0 END)    AS fuel_net,
          SUM(CASE WHEN category IN ('mm','ff') THEN net_amount ELSE 0 END) AS shop_net,
          SUM(net_amount) * 1.0 / COUNT(DISTINCT receipt_id)          AS avg_receipt,
          SUM(CASE WHEN has_loyalty=1 THEN 1 ELSE 0 END) * 100.0
            / COUNT(*)                                                 AS loyalty_pct
        FROM lines WHERE {w}
        GROUP BY azs_num
        ORDER BY net_amount DESC
    """, p)
    # Вычислить долю от суммарной выручки
    total = sum(r['net_amount'] or 0 for r in rows)
    for i, r in enumerate(rows):
        r['rank'] = i + 1
        r['revenue_share'] = (r['net_amount'] or 0) / total * 100 if total else 0
    return rows

def q_azs_daily_trend(con, d1, d2, azs=None):
    """Выручка по каждой АЗС по дням — для спарклайнов."""
    w, p = _where(d1, d2, azs=azs)
    return fetchall(con, f"""
        SELECT azs_num, substr(dt_str,1,10) AS date_str,
               SUM(net_amount) AS net_amount
        FROM lines WHERE {w}
        GROUP BY azs_num, date_str
        ORDER BY azs_num, date_str
    """, p)

# ─── Полная агрегация (один вызов) ───────────────────────────────────────────
def q_all(con, d1: str, d2: str, azs: Optional[list] = None) -> dict:
    """Возвращает все агрегаты за диапазон d1..d2, опционально фильтруя по АЗС."""
    # q_receipt_flags вычисляем один раз и передаём всем 5 функциям (cross + combo)
    flags = q_receipt_flags(con, d1, d2, azs=azs)
    return {
        'overall_kpi':       q_overall_kpi(con, d1, d2, azs),
        'by_category':       q_by_category(con, d1, d2, azs),
        'fuel_kpi':          q_fuel_kpi(con, d1, d2, azs),
        'fuel_by_product':   q_fuel_by_product(con, d1, d2, azs),
        'fuel_by_day':       q_fuel_by_day_product(con, d1, d2, azs),
        'fuel_by_azs':       q_fuel_by_azs(con, d1, d2, azs),
        'payments':          q_payments(con, d1, d2, azs),
        'smartpay_fuel':     q_smartpay_fuel(con, d1, d2, azs),
        'smartpay_product':  q_smartpay_fuel_product(con, d1, d2, azs),
        'smartpay_by_hour':  q_smartpay_by_hour(con, d1, d2, azs),
        'loyalty_kpi':       q_loyalty_kpi(con, d1, d2, azs),
        'loyalty_fuel':      q_loyalty_fuel(con, d1, d2, azs),
        'loyalty_by_azs':    q_loyalty_by_azs(con, d1, d2, azs),
        'arpu':              q_arpu(con, d1, d2, azs),
        'cross_combos':      q_cross_sell(con, d1, d2, azs, _flags=flags),
        'cross_conversion':  q_cross_sell_conversion(con, d1, d2, azs, _flags=flags),
        'cross_by_day':      q_cross_by_day(con, d1, d2, azs, _flags=flags),
        'azs_cross':         q_azs_cross(con, d1, d2, azs, _flags=flags),
        'discounts_kpi':     q_discounts_kpi(con, d1, d2, azs),
        'discounts_cat':     q_discounts_by_category(con, d1, d2, azs),
        'discounts_pay':     q_discounts_by_payment(con, d1, d2, azs),
        'discounts_loyalty': q_discounts_by_loyalty(con, d1, d2, azs),
        'discounts_azs':     q_discounts_by_azs(con, d1, d2, azs),
        'abc_mm':            q_abc(con, d1, d2, 'mm', azs),
        'abc_ff':            q_abc(con, d1, d2, 'ff', azs),
        'heatmap_fuel':      q_heatmap_fuel(con, d1, d2, azs),
        'heatmap_all':       q_heatmap_all(con, d1, d2, azs),
        'combo_segment':     q_combo_segment(con, d1, d2, azs, _flags=flags),
        'azs_rating':        q_azs_rating(con, d1, d2, azs),
        'azs_daily_trend':   q_azs_daily_trend(con, d1, d2, azs),
    }

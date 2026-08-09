import os
from sqlalchemy import create_engine, text

def run_star_transformations():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    db_file_path = os.path.join(project_root, "supply_chain_warehouse.db")
    
    db_url = f"sqlite:///{db_file_path}"
    engine = create_engine(db_url)
    
    sql_mart_views = [
        """
        DROP VIEW IF EXISTS mart_supplier_performance;
        """,
        """
        CREATE VIEW mart_supplier_performance AS
        SELECT 
            p.category_name,
            p.department_name,
            COUNT(f.order_id) AS total_orders,
            ROUND(SUM(f.sales), 2) AS gross_revenue,
            ROUND(SUM(f.order_profit_per_order), 2) AS net_profit,
            ROUND(AVG(f.is_late) * 100, 2) AS late_delivery_rate_pct,
            ROUND(AVG(f.shipping_delay_delta), 2) AS avg_days_delayed
        FROM fact_sales f
        INNER JOIN dim_products p ON f.product_card_id = p.product_card_id
        GROUP BY p.category_name, p.department_name;
        """,
        """
        DROP VIEW IF EXISTS mart_route_logistics_costs;
        """,
        """
        CREATE VIEW mart_route_logistics_costs AS
        SELECT 
            g.market,
            g.order_region,
            s.shipping_mode,
            COUNT(f.order_id) AS shipment_volume,
            ROUND(SUM(f.sales), 2) AS gross_sales,
            ROUND(SUM(f.order_profit_per_order), 2) AS net_profit,
            ROUND(SUM(f.sales - f.order_profit_per_order), 2) AS total_logistics_cost,
            ROUND(AVG(f.sales - f.order_profit_per_order), 2) AS avg_logistics_cost_per_order
        FROM fact_sales f
        INNER JOIN dim_geography g ON f.geo_id = g.geo_id
        INNER JOIN dim_shipping s ON f.shipping_id = s.shipping_id
        GROUP BY g.market, g.order_region, s.shipping_mode;
        """,
        """
        DROP VIEW IF EXISTS mart_fulfillment_constraints;
        """,
        """
        CREATE VIEW mart_fulfillment_constraints AS
        SELECT 
            s.shipping_mode,
            s.order_status,
            s.delivery_status,
            t.year,
            t.month,
            COUNT(f.order_id) AS total_delayed_orders,
            ROUND(AVG(f.shipping_delay_delta), 2) AS average_days_overdue
        FROM fact_sales f
        INNER JOIN dim_shipping s ON f.shipping_id = s.shipping_id
        INNER JOIN dim_time t ON f.time_id = t.time_id
        WHERE f.is_late = 1
        GROUP BY s.shipping_mode, s.order_status, s.delivery_status, t.year, t.month;
        """
    ]
    
    with engine.connect() as conn:
        for view_query in sql_mart_views:
            conn.execute(text(view_query))
        conn.commit()
    
    print("Star Schema Data Mart Views generated successfully.")

if __name__ == "__main__":
    run_star_transformations()
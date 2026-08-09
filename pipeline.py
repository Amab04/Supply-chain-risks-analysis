import os
import logging
import pandas as pd
from sqlalchemy import create_engine

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SupplyChainStarSchemaPipeline:
    def __init__(self, db_connection_str: str):
        self.engine = create_engine(db_connection_str)

    def optimize_types(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.columns:
            if df[col].dtype == 'object':
                if df[col].nunique() / len(df) < 0.5:
                    df[col] = df[col].astype('category')
            elif df[col].dtype in ['int64', 'int32']:
                df[col] = pd.to_numeric(df[col], downcast='integer')
            elif df[col].dtype in ['float64', 'float32']:
                df[col] = pd.to_numeric(df[col], downcast='float')
        return df

    def run_pipeline(self, file_path: str):
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            raise FileNotFoundError

        logging.info("Starting raw data ingestion and column normalization...")
        raw_df = pd.read_csv(file_path, encoding='latin1')
        
        raw_df.columns = (
            raw_df.columns.str.strip()
            .str.lower()
            .str.replace(' ', '_')
            .str.replace('(', '')
            .str.replace(')', '')
        )

        logging.info("Extracting Dim_Customers...")
        dim_customers = raw_df[[
            'customer_id', 'customer_fname', 'customer_lname', 
            'customer_segment', 'customer_state', 'customer_city'
        ]].drop_duplicates(subset=['customer_id']).copy()
        
        logging.info("Extracting Dim_Products...")
        dim_products = raw_df[[
            'product_card_id', 'product_name', 'category_name', 
            'department_name', 'product_price'
        ]].drop_duplicates(subset=['product_card_id']).copy()

        logging.info("Extracting Dim_Geography and generating surrogate keys...")
        geo_cols = ['market', 'order_region', 'order_country', 'order_city']
        dim_geography = raw_df[geo_cols].drop_duplicates().reset_index(drop=True)
        dim_geography['geo_id'] = dim_geography.index + 1

        logging.info("Extracting Dim_Shipping and generating surrogate keys...")
        ship_cols = ['shipping_mode', 'delivery_status', 'order_status']
        dim_shipping = raw_df[ship_cols].drop_duplicates().reset_index(drop=True)
        dim_shipping['shipping_id'] = dim_shipping.index + 1

        logging.info("Extracting Dim_Time...")
        raw_df['order_date_parsed'] = pd.to_datetime(raw_df['order_date_dateorders'], errors='coerce')
        dim_time = pd.DataFrame()
        dim_time['time_id'] = raw_df['order_date_parsed'].dt.strftime('%Y%m%d')
        dim_time['order_date'] = raw_df['order_date_parsed']
        dim_time['year'] = raw_df['order_date_parsed'].dt.year
        dim_time['quarter'] = raw_df['order_date_parsed'].dt.quarter
        dim_time['month'] = raw_df['order_date_parsed'].dt.month
        dim_time['day'] = raw_df['order_date_parsed'].dt.day
        dim_time['day_of_week'] = raw_df['order_date_parsed'].dt.day_name()
        dim_time = dim_time.dropna(subset=['time_id']).drop_duplicates(subset=['time_id'])

        logging.info("Compiling Fact_Sales...")
        raw_df['shipping_delay_delta'] = raw_df['days_for_shipping_real'] - raw_df['days_for_shipment_scheduled']
        raw_df['is_late'] = (raw_df['shipping_delay_delta'] > 0).astype(int)
        raw_df['time_id'] = raw_df['order_date_parsed'].dt.strftime('%Y%m%d')

        fact_sales = raw_df.merge(dim_geography, on=geo_cols, how='left')
        fact_sales = fact_sales.merge(dim_shipping, on=ship_cols, how='left')

        fact_sales_cols = [
            'order_id', 'order_item_id', 'customer_id', 'product_card_id', 
            'geo_id', 'shipping_id', 'time_id', 'sales', 'order_profit_per_order', 
            'days_for_shipping_real', 'days_for_shipment_scheduled', 
            'shipping_delay_delta', 'is_late'
        ]
        fact_sales = fact_sales[fact_sales_cols].copy()
        
        fill_zeros = ['sales', 'order_profit_per_order', 'days_for_shipping_real', 'days_for_shipment_scheduled', 'shipping_delay_delta', 'is_late']
        for col in fill_zeros:
            fact_sales[col] = fact_sales[col].fillna(0)

        dim_customers = self.optimize_types(dim_customers)
        dim_products = self.optimize_types(dim_products)
        dim_geography = self.optimize_types(dim_geography)
        dim_shipping = self.optimize_types(dim_shipping)
        dim_time = self.optimize_types(dim_time)
        fact_sales = self.optimize_types(fact_sales)

        tables = {
            'dim_customers': dim_customers,
            'dim_products': dim_products,
            'dim_geography': dim_geography,
            'dim_shipping': dim_shipping,
            'dim_time': dim_time,
            'fact_sales': fact_sales
        }

        for table_name, table_df in tables.items():
            logging.info(f"Loading {table_name} into SQL Data Warehouse...")
            table_df.to_sql(table_name, con=self.engine, if_exists='replace', index=False)

        logging.info("Star Schema pipeline fully executed successfully.")

if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
    
    DATA_SOURCE = os.path.join(PROJECT_ROOT, "data", "DataCoSupplyChainDataset.csv")
    DB_FILE_PATH = os.path.join(PROJECT_ROOT, "supply_chain_warehouse.db")
    DB_PATH = f"sqlite:///{DB_FILE_PATH}"

    pipeline = SupplyChainStarSchemaPipeline(DB_PATH)
    pipeline.run_pipeline(DATA_SOURCE)
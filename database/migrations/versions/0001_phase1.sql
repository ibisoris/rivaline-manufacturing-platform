CREATE TABLE customers (
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_customers PRIMARY KEY (id),
	CONSTRAINT uq_customers_code UNIQUE (code),
	CONSTRAINT uq_customers_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE etl_runs (
	code VARCHAR(80) NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	status VARCHAR(20) NOT NULL,
	rows_read INTEGER NOT NULL,
	rows_loaded INTEGER NOT NULL,
	rows_rejected INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_etl_runs PRIMARY KEY (id),
	CONSTRAINT ck_etl_runs_status CHECK (status IN ('running', 'succeeded', 'failed')),
	CONSTRAINT ck_etl_runs_counts CHECK (rows_read >= 0 AND rows_loaded >= 0 AND rows_rejected >= 0 AND rows_loaded + rows_rejected <= rows_read),
	CONSTRAINT ck_etl_runs_dates CHECK (finished_at IS NULL OR finished_at >= started_at),
	CONSTRAINT uq_etl_runs_code UNIQUE (code),
	CONSTRAINT uq_etl_runs_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE products (
	unit_of_measure VARCHAR(12) NOT NULL,
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_products PRIMARY KEY (id),
	CONSTRAINT uq_products_code UNIQUE (code),
	CONSTRAINT uq_products_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE suppliers (
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_suppliers PRIMARY KEY (id),
	CONSTRAINT uq_suppliers_code UNIQUE (code),
	CONSTRAINT uq_suppliers_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE warehouses (
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_warehouses PRIMARY KEY (id),
	CONSTRAINT uq_warehouses_code UNIQUE (code),
	CONSTRAINT uq_warehouses_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE bills_of_material (
	code VARCHAR(40) NOT NULL,
	product_id INTEGER NOT NULL,
	version INTEGER NOT NULL,
	output_quantity NUMERIC(18, 6) NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_bills_of_material PRIMARY KEY (id),
	CONSTRAINT uq_bills_of_material_product_id UNIQUE (product_id, version),
	CONSTRAINT uq_bills_of_material_id UNIQUE (id, product_id),
	CONSTRAINT ck_bills_of_material_positive CHECK (output_quantity > 0 AND version > 0),
	CONSTRAINT ck_bills_of_material_status CHECK (status IN ('draft', 'active', 'retired')),
	CONSTRAINT uq_bills_of_material_code UNIQUE (code),
	CONSTRAINT fk_bills_of_material_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_bills_of_material_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_bills_of_material_product_id ON bills_of_material (product_id);

CREATE TABLE data_quality_issues (
	etl_run_id INTEGER NOT NULL,
	entity_name VARCHAR(80) NOT NULL,
	rule_code VARCHAR(80) NOT NULL,
	severity VARCHAR(20) NOT NULL,
	message VARCHAR(500) NOT NULL,
	details JSON,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_data_quality_issues PRIMARY KEY (id),
	CONSTRAINT ck_data_quality_issues_severity CHECK (severity IN ('warning', 'error')),
	CONSTRAINT ck_data_quality_issues_status CHECK (status IN ('open', 'resolved', 'accepted')),
	CONSTRAINT fk_data_quality_issues_etl_run_id_etl_runs FOREIGN KEY(etl_run_id) REFERENCES etl_runs (id),
	CONSTRAINT uq_data_quality_issues_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_data_quality_issues_etl_run_id ON data_quality_issues (etl_run_id);

CREATE TABLE demand_forecasts (
	product_id INTEGER NOT NULL,
	period_start DATE NOT NULL,
	period_end DATE NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	model_version VARCHAR(80) NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_demand_forecasts PRIMARY KEY (id),
	CONSTRAINT uq_demand_forecasts_product_id UNIQUE (product_id, period_start, period_end, model_version, generated_at),
	CONSTRAINT ck_demand_forecasts_forecast CHECK (quantity >= 0 AND period_end >= period_start),
	CONSTRAINT fk_demand_forecasts_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_demand_forecasts_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_demand_forecasts_product_id ON demand_forecasts (product_id);

CREATE TABLE purchase_orders (
	code VARCHAR(40) NOT NULL,
	supplier_id INTEGER NOT NULL,
	order_date DATE NOT NULL,
	expected_date DATE NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_purchase_orders PRIMARY KEY (id),
	CONSTRAINT ck_purchase_orders_dates CHECK (expected_date >= order_date),
	CONSTRAINT ck_purchase_orders_status CHECK (status IN ('open', 'confirmed', 'received', 'cancelled')),
	CONSTRAINT uq_purchase_orders_code UNIQUE (code),
	CONSTRAINT fk_purchase_orders_supplier_id_suppliers FOREIGN KEY(supplier_id) REFERENCES suppliers (id),
	CONSTRAINT uq_purchase_orders_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_purchase_orders_supplier_id ON purchase_orders (supplier_id);

CREATE TABLE raw_materials (
	category VARCHAR(30) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	preferred_supplier_id INTEGER,
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	active BOOLEAN NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_raw_materials PRIMARY KEY (id),
	CONSTRAINT ck_raw_materials_category CHECK (category IN ('pigment', 'resin', 'solvent', 'additive')),
	CONSTRAINT fk_raw_materials_preferred_supplier_id_suppliers FOREIGN KEY(preferred_supplier_id) REFERENCES suppliers (id),
	CONSTRAINT uq_raw_materials_code UNIQUE (code),
	CONSTRAINT uq_raw_materials_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_raw_materials_preferred_supplier_id ON raw_materials (preferred_supplier_id);

CREATE TABLE sales_orders (
	code VARCHAR(40) NOT NULL,
	customer_id INTEGER NOT NULL,
	order_date DATE NOT NULL,
	required_date DATE NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_sales_orders PRIMARY KEY (id),
	CONSTRAINT ck_sales_orders_dates CHECK (required_date >= order_date),
	CONSTRAINT ck_sales_orders_status CHECK (status IN ('open', 'confirmed', 'fulfilled', 'cancelled')),
	CONSTRAINT uq_sales_orders_code UNIQUE (code),
	CONSTRAINT fk_sales_orders_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id),
	CONSTRAINT uq_sales_orders_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_sales_orders_customer_id ON sales_orders (customer_id);

CREATE TABLE shipments (
	code VARCHAR(40) NOT NULL,
	warehouse_id INTEGER NOT NULL,
	shipped_at TIMESTAMP WITH TIME ZONE,
	status VARCHAR(20) NOT NULL,
	tracking_reference VARCHAR(100),
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_shipments PRIMARY KEY (id),
	CONSTRAINT ck_shipments_status CHECK (status IN ('pending', 'dispatched', 'delivered', 'cancelled')),
	CONSTRAINT uq_shipments_code UNIQUE (code),
	CONSTRAINT fk_shipments_warehouse_id_warehouses FOREIGN KEY(warehouse_id) REFERENCES warehouses (id),
	CONSTRAINT uq_shipments_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_shipments_warehouse_id ON shipments (warehouse_id);

CREATE TABLE bill_of_material_lines (
	bom_id INTEGER NOT NULL,
	raw_material_id INTEGER NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_bill_of_material_lines PRIMARY KEY (id),
	CONSTRAINT uq_bill_of_material_lines_bom_id UNIQUE (bom_id, raw_material_id),
	CONSTRAINT ck_bill_of_material_lines_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_bill_of_material_lines_bom_id_bills_of_material FOREIGN KEY(bom_id) REFERENCES bills_of_material (id),
	CONSTRAINT fk_bill_of_material_lines_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT uq_bill_of_material_lines_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_bill_of_material_lines_bom_id ON bill_of_material_lines (bom_id);

CREATE INDEX ix_bill_of_material_lines_raw_material_id ON bill_of_material_lines (raw_material_id);

CREATE TABLE inventory (
	warehouse_id INTEGER NOT NULL,
	product_id INTEGER,
	raw_material_id INTEGER,
	lot_code VARCHAR(80) NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	reserved_quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_inventory PRIMARY KEY (id),
	CONSTRAINT ck_inventory_one_item CHECK ((product_id IS NOT NULL AND raw_material_id IS NULL) OR (product_id IS NULL AND raw_material_id IS NOT NULL)),
	CONSTRAINT ck_inventory_quantities CHECK (quantity >= 0 AND reserved_quantity >= 0 AND reserved_quantity <= quantity),
	CONSTRAINT uq_inventory_product_lot UNIQUE (warehouse_id, product_id, lot_code),
	CONSTRAINT uq_inventory_material_lot UNIQUE (warehouse_id, raw_material_id, lot_code),
	CONSTRAINT fk_inventory_warehouse_id_warehouses FOREIGN KEY(warehouse_id) REFERENCES warehouses (id),
	CONSTRAINT fk_inventory_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT fk_inventory_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT uq_inventory_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_inventory_product_id ON inventory (product_id);

CREATE INDEX ix_inventory_raw_material_id ON inventory (raw_material_id);

CREATE INDEX ix_inventory_warehouse_id ON inventory (warehouse_id);

CREATE TABLE purchase_order_lines (
	purchase_order_id INTEGER NOT NULL,
	line_number INTEGER NOT NULL,
	raw_material_id INTEGER NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	unit_price_gbp NUMERIC(18, 2) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_purchase_order_lines PRIMARY KEY (id),
	CONSTRAINT uq_purchase_order_lines_purchase_order_id UNIQUE (purchase_order_id, line_number),
	CONSTRAINT uq_purchase_order_lines_id UNIQUE (id, raw_material_id),
	CONSTRAINT ck_purchase_order_lines_values CHECK (quantity > 0 AND unit_price_gbp >= 0 AND line_number > 0),
	CONSTRAINT fk_purchase_order_lines_purchase_order_id_purchase_orders FOREIGN KEY(purchase_order_id) REFERENCES purchase_orders (id),
	CONSTRAINT fk_purchase_order_lines_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT uq_purchase_order_lines_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_purchase_order_lines_purchase_order_id ON purchase_order_lines (purchase_order_id);

CREATE INDEX ix_purchase_order_lines_raw_material_id ON purchase_order_lines (raw_material_id);

CREATE TABLE reorder_recommendations (
	raw_material_id INTEGER NOT NULL,
	warehouse_id INTEGER NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_reorder_recommendations PRIMARY KEY (id),
	CONSTRAINT ck_reorder_recommendations_positive_quantity CHECK (quantity > 0),
	CONSTRAINT ck_reorder_recommendations_status CHECK (status IN ('proposed', 'accepted', 'dismissed')),
	CONSTRAINT fk_reorder_recommendations_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT fk_reorder_recommendations_warehouse_id_warehouses FOREIGN KEY(warehouse_id) REFERENCES warehouses (id),
	CONSTRAINT uq_reorder_recommendations_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_reorder_recommendations_raw_material_id ON reorder_recommendations (raw_material_id);

CREATE INDEX ix_reorder_recommendations_warehouse_id ON reorder_recommendations (warehouse_id);

CREATE TABLE sales_order_lines (
	sales_order_id INTEGER NOT NULL,
	line_number INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	unit_price_gbp NUMERIC(18, 2) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_sales_order_lines PRIMARY KEY (id),
	CONSTRAINT uq_sales_order_lines_sales_order_id UNIQUE (sales_order_id, line_number),
	CONSTRAINT uq_sales_order_lines_id UNIQUE (id, product_id),
	CONSTRAINT ck_sales_order_lines_values CHECK (quantity > 0 AND unit_price_gbp >= 0 AND line_number > 0),
	CONSTRAINT fk_sales_order_lines_sales_order_id_sales_orders FOREIGN KEY(sales_order_id) REFERENCES sales_orders (id),
	CONSTRAINT fk_sales_order_lines_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_sales_order_lines_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_sales_order_lines_product_id ON sales_order_lines (product_id);

CREATE INDEX ix_sales_order_lines_sales_order_id ON sales_order_lines (sales_order_id);

CREATE TABLE inventory_transactions (
	inventory_id INTEGER NOT NULL,
	quantity_delta NUMERIC(18, 6) NOT NULL,
	transaction_type VARCHAR(24) NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	reference VARCHAR(160) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_inventory_transactions PRIMARY KEY (id),
	CONSTRAINT ck_inventory_transactions_nonzero CHECK (quantity_delta <> 0),
	CONSTRAINT ck_inventory_transactions_type CHECK (transaction_type IN ('receipt', 'issue', 'adjustment')),
	CONSTRAINT ck_inventory_transactions_direction CHECK (transaction_type = 'adjustment' OR (transaction_type = 'receipt' AND quantity_delta > 0) OR (transaction_type = 'issue' AND quantity_delta < 0)),
	CONSTRAINT fk_inventory_transactions_inventory_id_inventory FOREIGN KEY(inventory_id) REFERENCES inventory (id),
	CONSTRAINT uq_inventory_transactions_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_inventory_transactions_inventory_id ON inventory_transactions (inventory_id);

CREATE TABLE production_orders (
	code VARCHAR(40) NOT NULL,
	product_id INTEGER NOT NULL,
	bom_id INTEGER NOT NULL,
	sales_order_line_id INTEGER,
	planned_quantity NUMERIC(18, 6) NOT NULL,
	planned_start DATE NOT NULL,
	planned_end DATE NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_orders PRIMARY KEY (id),
	CONSTRAINT fk_production_orders_bom_id_bills_of_material FOREIGN KEY(bom_id, product_id) REFERENCES bills_of_material (id, product_id),
	CONSTRAINT fk_production_orders_sales_order_line_id_sales_order_lines FOREIGN KEY(sales_order_line_id, product_id) REFERENCES sales_order_lines (id, product_id),
	CONSTRAINT uq_production_orders_id UNIQUE (id, product_id),
	CONSTRAINT ck_production_orders_plan CHECK (planned_quantity > 0 AND planned_end >= planned_start),
	CONSTRAINT ck_production_orders_status CHECK (status IN ('planned', 'released', 'completed', 'cancelled')),
	CONSTRAINT uq_production_orders_code UNIQUE (code),
	CONSTRAINT fk_production_orders_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_production_orders_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_orders_bom_id ON production_orders (bom_id);

CREATE INDEX ix_production_orders_product_id ON production_orders (product_id);

CREATE INDEX ix_production_orders_sales_order_line_id ON production_orders (sales_order_line_id);

CREATE TABLE production_batches (
	code VARCHAR(80) NOT NULL,
	production_order_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	actual_quantity NUMERIC(18, 6) NOT NULL,
	status VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_batches PRIMARY KEY (id),
	CONSTRAINT fk_production_batches_production_order_id_production_orders FOREIGN KEY(production_order_id, product_id) REFERENCES production_orders (id, product_id),
	CONSTRAINT uq_production_batches_id UNIQUE (id, product_id),
	CONSTRAINT ck_production_batches_quantity CHECK (actual_quantity >= 0),
	CONSTRAINT ck_production_batches_status CHECK (status IN ('pending', 'in_progress', 'quarantined', 'released', 'rejected')),
	CONSTRAINT uq_production_batches_code UNIQUE (code),
	CONSTRAINT fk_production_batches_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_production_batches_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_batches_product_id ON production_batches (product_id);

CREATE INDEX ix_production_batches_production_order_id ON production_batches (production_order_id);

CREATE TABLE batch_material_consumption (
	production_batch_id INTEGER NOT NULL,
	raw_material_id INTEGER NOT NULL,
	purchase_order_line_id INTEGER NOT NULL,
	supplier_lot_code VARCHAR(80) NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_batch_material_consumption PRIMARY KEY (id),
	CONSTRAINT fk_batch_material_consumption_purchase_order_line_id_pu_a88b FOREIGN KEY(purchase_order_line_id, raw_material_id) REFERENCES purchase_order_lines (id, raw_material_id),
	CONSTRAINT ck_batch_material_consumption_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_batch_material_consumption_production_batch_id_produ_086c FOREIGN KEY(production_batch_id) REFERENCES production_batches (id),
	CONSTRAINT fk_batch_material_consumption_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT uq_batch_material_consumption_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_batch_material_consumption_production_batch_id ON batch_material_consumption (production_batch_id);

CREATE INDEX ix_batch_material_consumption_purchase_order_line_id ON batch_material_consumption (purchase_order_line_id);

CREATE INDEX ix_batch_material_consumption_raw_material_id ON batch_material_consumption (raw_material_id);

CREATE TABLE quality_inspections (
	production_batch_id INTEGER NOT NULL,
	inspected_at TIMESTAMP WITH TIME ZONE NOT NULL,
	test_code VARCHAR(40) NOT NULL,
	measured_value NUMERIC(18, 6) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	result VARCHAR(20) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_quality_inspections PRIMARY KEY (id),
	CONSTRAINT ck_quality_inspections_result CHECK (result IN ('pass', 'fail', 'pending')),
	CONSTRAINT fk_quality_inspections_production_batch_id_production_batches FOREIGN KEY(production_batch_id) REFERENCES production_batches (id),
	CONSTRAINT uq_quality_inspections_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_quality_inspections_production_batch_id ON quality_inspections (production_batch_id);

CREATE TABLE shipment_lines (
	shipment_id INTEGER NOT NULL,
	sales_order_line_id INTEGER NOT NULL,
	production_batch_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_shipment_lines PRIMARY KEY (id),
	CONSTRAINT fk_shipment_lines_sales_order_line_id_sales_order_lines FOREIGN KEY(sales_order_line_id, product_id) REFERENCES sales_order_lines (id, product_id),
	CONSTRAINT fk_shipment_lines_production_batch_id_production_batches FOREIGN KEY(production_batch_id, product_id) REFERENCES production_batches (id, product_id),
	CONSTRAINT uq_shipment_lines_shipment_id UNIQUE (shipment_id, sales_order_line_id, production_batch_id),
	CONSTRAINT ck_shipment_lines_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_shipment_lines_shipment_id_shipments FOREIGN KEY(shipment_id) REFERENCES shipments (id),
	CONSTRAINT fk_shipment_lines_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_shipment_lines_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_shipment_lines_product_id ON shipment_lines (product_id);

CREATE INDEX ix_shipment_lines_production_batch_id ON shipment_lines (production_batch_id);

CREATE INDEX ix_shipment_lines_sales_order_line_id ON shipment_lines (sales_order_line_id);

CREATE INDEX ix_shipment_lines_shipment_id ON shipment_lines (shipment_id);

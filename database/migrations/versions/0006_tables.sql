CREATE TABLE production_resources (
	code VARCHAR(40) NOT NULL,
	name VARCHAR(160) NOT NULL,
	monthly_hours NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_resources PRIMARY KEY (id),
	CONSTRAINT ck_production_resources_hours CHECK (monthly_hours >= 0),
	CONSTRAINT uq_production_resources_code UNIQUE (code),
	CONSTRAINT uq_production_resources_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE production_plan_runs (
	code VARCHAR(64) NOT NULL,
	algorithm_version VARCHAR(40) NOT NULL,
	forecast_run_id INTEGER NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	inputs JSON NOT NULL,
	report JSON NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_plan_runs PRIMARY KEY (id),
	CONSTRAINT uq_production_plan_runs_code UNIQUE (code),
	CONSTRAINT fk_production_plan_runs_forecast_run_id_forecast_runs FOREIGN KEY(forecast_run_id) REFERENCES forecast_runs (id),
	CONSTRAINT uq_production_plan_runs_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_plan_runs_forecast_run_id ON production_plan_runs (forecast_run_id);

CREATE TABLE production_policies (
	product_id INTEGER NOT NULL,
	resource_id INTEGER NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	minimum_batch NUMERIC(18, 6) NOT NULL,
	preferred_batch NUMERIC(18, 6) NOT NULL,
	maximum_batch NUMERIC(18, 6) NOT NULL,
	units_per_hour NUMERIC(18, 6) NOT NULL,
	priority INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_policies PRIMARY KEY (id),
	CONSTRAINT ck_production_policies_batch_bounds CHECK (minimum_batch > 0 AND preferred_batch >= minimum_batch AND maximum_batch >= preferred_batch),
	CONSTRAINT ck_production_policies_rate_priority CHECK (units_per_hour > 0 AND priority >= 1),
	CONSTRAINT uq_production_policies_product_id UNIQUE (product_id),
	CONSTRAINT fk_production_policies_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT fk_production_policies_resource_id_production_resources FOREIGN KEY(resource_id) REFERENCES production_resources (id),
	CONSTRAINT uq_production_policies_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_policies_product_id ON production_policies (product_id);

CREATE INDEX ix_production_policies_resource_id ON production_policies (resource_id);

CREATE TABLE production_capacity_results (
	plan_run_id INTEGER NOT NULL,
	resource_id INTEGER NOT NULL,
	resource_code VARCHAR(40) NOT NULL,
	period_start DATE NOT NULL,
	required_hours NUMERIC(18, 6) NOT NULL,
	available_hours NUMERIC(18, 6) NOT NULL,
	allocated_hours NUMERIC(18, 6) NOT NULL,
	overload_hours NUMERIC(18, 6) NOT NULL,
	utilisation_pct NUMERIC(18, 6),
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_capacity_results PRIMARY KEY (id),
	CONSTRAINT uq_production_capacity_results_plan_run_id UNIQUE (plan_run_id, resource_id, period_start),
	CONSTRAINT ck_production_capacity_results_hours CHECK (required_hours >= 0 AND available_hours >= 0 AND allocated_hours >= 0 AND allocated_hours <= available_hours AND overload_hours >= 0 AND (utilisation_pct IS NULL OR utilisation_pct >= 0)),
	CONSTRAINT fk_production_capacity_results_plan_run_id_production_plan_runs FOREIGN KEY(plan_run_id) REFERENCES production_plan_runs (id),
	CONSTRAINT fk_production_capacity_results_resource_id_production_resources FOREIGN KEY(resource_id) REFERENCES production_resources (id),
	CONSTRAINT uq_production_capacity_results_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_capacity_results_plan_run_id ON production_capacity_results (plan_run_id);

CREATE INDEX ix_production_capacity_results_resource_id ON production_capacity_results (resource_id);

CREATE TABLE production_plan_lines (
	plan_run_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	resource_id INTEGER NOT NULL,
	period_start DATE NOT NULL,
	product_code VARCHAR(40) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	gross_demand NUMERIC(18, 6) NOT NULL,
	inventory_offset NUMERIC(18, 6) NOT NULL,
	surplus_offset NUMERIC(18, 6) NOT NULL,
	net_requirement NUMERIC(18, 6) NOT NULL,
	proposed_quantity NUMERIC(18, 6) NOT NULL,
	allocated_quantity NUMERIC(18, 6) NOT NULL,
	unmet_quantity NUMERIC(18, 6) NOT NULL,
	batch_count INTEGER NOT NULL,
	required_hours NUMERIC(18, 6) NOT NULL,
	available_hours NUMERIC(18, 6) NOT NULL,
	allocated_hours NUMERIC(18, 6) NOT NULL,
	overload_hours NUMERIC(18, 6) NOT NULL,
	utilisation_pct NUMERIC(18, 6),
	status VARCHAR(40) NOT NULL,
	explanation VARCHAR(2000) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_plan_lines PRIMARY KEY (id),
	CONSTRAINT uq_production_plan_lines_plan_run_id UNIQUE (plan_run_id, product_id, period_start),
	CONSTRAINT ck_production_plan_lines_quantities CHECK (gross_demand >= 0 AND inventory_offset >= 0 AND surplus_offset >= 0 AND net_requirement >= 0 AND proposed_quantity >= net_requirement AND allocated_quantity >= 0 AND allocated_quantity <= proposed_quantity AND unmet_quantity >= 0 AND batch_count >= 0),
	CONSTRAINT ck_production_plan_lines_hours CHECK (required_hours >= 0 AND available_hours >= 0 AND allocated_hours >= 0 AND allocated_hours <= available_hours AND overload_hours >= 0 AND (utilisation_pct IS NULL OR utilisation_pct >= 0)),
	CONSTRAINT ck_production_plan_lines_status CHECK (status IN ('FEASIBLE', 'MATERIAL_CONSTRAINED', 'CAPACITY_CONSTRAINED', 'MATERIAL_AND_CAPACITY_CONSTRAINED')),
	CONSTRAINT fk_production_plan_lines_plan_run_id_production_plan_runs FOREIGN KEY(plan_run_id) REFERENCES production_plan_runs (id),
	CONSTRAINT fk_production_plan_lines_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT fk_production_plan_lines_resource_id_production_resources FOREIGN KEY(resource_id) REFERENCES production_resources (id),
	CONSTRAINT uq_production_plan_lines_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_plan_lines_plan_run_id ON production_plan_lines (plan_run_id);

CREATE INDEX ix_production_plan_lines_product_id ON production_plan_lines (product_id);

CREATE INDEX ix_production_plan_lines_resource_id ON production_plan_lines (resource_id);

CREATE TABLE production_material_results (
	plan_line_id INTEGER NOT NULL,
	raw_material_id INTEGER NOT NULL,
	material_code VARCHAR(40) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	required_quantity NUMERIC(18, 6) NOT NULL,
	available_quantity NUMERIC(18, 6) NOT NULL,
	shortage_quantity NUMERIC(18, 6) NOT NULL,
	allocated_quantity NUMERIC(18, 6) NOT NULL,
	remaining_quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_production_material_results PRIMARY KEY (id),
	CONSTRAINT uq_production_material_results_plan_line_id UNIQUE (plan_line_id, raw_material_id),
	CONSTRAINT ck_production_material_results_quantities CHECK (required_quantity >= 0 AND available_quantity >= 0 AND shortage_quantity >= 0 AND allocated_quantity >= 0 AND allocated_quantity <= required_quantity AND remaining_quantity >= 0),
	CONSTRAINT fk_production_material_results_plan_line_id_production__ab84 FOREIGN KEY(plan_line_id) REFERENCES production_plan_lines (id),
	CONSTRAINT fk_production_material_results_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT uq_production_material_results_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_production_material_results_plan_line_id ON production_material_results (plan_line_id);

CREATE INDEX ix_production_material_results_raw_material_id ON production_material_results (raw_material_id);

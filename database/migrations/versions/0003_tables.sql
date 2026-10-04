CREATE TABLE planning_policies (
	raw_material_id INTEGER NOT NULL,
	warehouse_id INTEGER NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	safety_stock NUMERIC(18, 6) NOT NULL,
	reorder_point NUMERIC(18, 6) NOT NULL,
	target_stock NUMERIC(18, 6) NOT NULL,
	minimum_order_quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_planning_policies PRIMARY KEY (id),
	CONSTRAINT ck_planning_policies_thresholds CHECK (safety_stock >= 0 AND reorder_point >= safety_stock AND target_stock > reorder_point AND minimum_order_quantity >= 0),
	CONSTRAINT uq_planning_policies_raw_material_id UNIQUE (raw_material_id),
	CONSTRAINT fk_planning_policies_raw_material_id_raw_materials FOREIGN KEY(raw_material_id) REFERENCES raw_materials (id),
	CONSTRAINT fk_planning_policies_warehouse_id_warehouses FOREIGN KEY(warehouse_id) REFERENCES warehouses (id),
	CONSTRAINT uq_planning_policies_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_planning_policies_raw_material_id ON planning_policies (raw_material_id);

CREATE INDEX ix_planning_policies_warehouse_id ON planning_policies (warehouse_id);

CREATE TABLE planning_runs (
	code VARCHAR(64) NOT NULL,
	algorithm_version VARCHAR(40) NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	inputs JSON NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_planning_runs PRIMARY KEY (id),
	CONSTRAINT uq_planning_runs_code UNIQUE (code),
	CONSTRAINT uq_planning_runs_source_system UNIQUE (source_system, source_record_id)
);

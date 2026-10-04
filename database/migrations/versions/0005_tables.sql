CREATE TABLE demand_observations (
	dataset_code VARCHAR(60) NOT NULL,
	product_id INTEGER NOT NULL,
	period_start DATE NOT NULL,
	quantity NUMERIC(18, 6) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	file_sha256 VARCHAR(64) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_demand_observations PRIMARY KEY (id),
	CONSTRAINT ck_demand_observations_quantity CHECK (quantity >= 0),
	CONSTRAINT fk_demand_observations_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_demand_observations_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_demand_observations_dataset_code ON demand_observations (dataset_code);

CREATE INDEX ix_demand_observations_product_id ON demand_observations (product_id);

CREATE TABLE forecast_runs (
	code VARCHAR(64) NOT NULL,
	dataset_code VARCHAR(60) NOT NULL,
	algorithm_version VARCHAR(40) NOT NULL,
	training_cutoff DATE NOT NULL,
	horizon INTEGER NOT NULL,
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	inputs JSON NOT NULL,
	report JSON NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_forecast_runs PRIMARY KEY (id),
	CONSTRAINT ck_forecast_runs_horizon CHECK (horizon = 3),
	CONSTRAINT uq_forecast_runs_code UNIQUE (code),
	CONSTRAINT uq_forecast_runs_source_system UNIQUE (source_system, source_record_id)
);

CREATE TABLE forecast_metrics (
	forecast_run_id INTEGER NOT NULL,
	product_id INTEGER,
	scope_key VARCHAR(60) NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	model_name VARCHAR(30) NOT NULL,
	evaluation_split VARCHAR(20) NOT NULL,
	observations INTEGER NOT NULL,
	mae NUMERIC(18, 6) NOT NULL,
	rmse NUMERIC(18, 6) NOT NULL,
	wape_pct NUMERIC(18, 6),
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_forecast_metrics PRIMARY KEY (id),
	CONSTRAINT uq_forecast_metrics_forecast_run_id UNIQUE (forecast_run_id, scope_key, model_name, evaluation_split),
	CONSTRAINT ck_forecast_metrics_metrics CHECK (observations > 0 AND mae >= 0 AND rmse >= 0 AND (wape_pct IS NULL OR wape_pct >= 0)),
	CONSTRAINT ck_forecast_metrics_split CHECK (evaluation_split IN ('validation', 'test')),
	CONSTRAINT ck_forecast_metrics_model CHECK (model_name IN ('naive', 'moving_average', 'linear_trend')),
	CONSTRAINT fk_forecast_metrics_forecast_run_id_forecast_runs FOREIGN KEY(forecast_run_id) REFERENCES forecast_runs (id),
	CONSTRAINT fk_forecast_metrics_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_forecast_metrics_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_forecast_metrics_forecast_run_id ON forecast_metrics (forecast_run_id);

CREATE INDEX ix_forecast_metrics_product_id ON forecast_metrics (product_id);

CREATE TABLE forecast_backtests (
	forecast_run_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	unit_of_measure VARCHAR(12) NOT NULL,
	model_name VARCHAR(30) NOT NULL,
	evaluation_split VARCHAR(20) NOT NULL,
	training_cutoff DATE NOT NULL,
	period_start DATE NOT NULL,
	actual_quantity NUMERIC(18, 6) NOT NULL,
	predicted_quantity NUMERIC(18, 6) NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_system VARCHAR(80) NOT NULL,
	source_record_id VARCHAR(160),
	CONSTRAINT pk_forecast_backtests PRIMARY KEY (id),
	CONSTRAINT uq_forecast_backtests_forecast_run_id UNIQUE (forecast_run_id, product_id, model_name, training_cutoff, period_start),
	CONSTRAINT ck_forecast_backtests_values CHECK (actual_quantity >= 0 AND predicted_quantity >= 0 AND period_start > training_cutoff),
	CONSTRAINT ck_forecast_backtests_split CHECK (evaluation_split IN ('validation', 'test')),
	CONSTRAINT ck_forecast_backtests_model CHECK (model_name IN ('naive', 'moving_average', 'linear_trend')),
	CONSTRAINT fk_forecast_backtests_forecast_run_id_forecast_runs FOREIGN KEY(forecast_run_id) REFERENCES forecast_runs (id),
	CONSTRAINT fk_forecast_backtests_product_id_products FOREIGN KEY(product_id) REFERENCES products (id),
	CONSTRAINT uq_forecast_backtests_source_system UNIQUE (source_system, source_record_id)
);

CREATE INDEX ix_forecast_backtests_forecast_run_id ON forecast_backtests (forecast_run_id);

CREATE INDEX ix_forecast_backtests_product_id ON forecast_backtests (product_id);

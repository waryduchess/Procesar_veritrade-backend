USE veritrade;

-- ---------- Tabla principal (fact) ----------
CREATE TABLE importaciones (
    id                       BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Identificadores de la operación
    partida_arancelaria      VARCHAR(20)  NOT NULL,
    descripcion_partida      VARCHAR(500),
    aduana                   VARCHAR(120),
    dua                      VARCHAR(50),
    numero_serie             VARCHAR(20),
    fecha                    DATE,
    codigo_tributario        VARCHAR(20),

    -- Importador
    importador               VARCHAR(255),
    ciudad_importador        VARCHAR(120),
    direccion_importador     VARCHAR(500),
    estado_importador        VARCHAR(120),

    -- Exportador
    exportador               VARCHAR(255),
    ciudad_exportador        VARCHAR(120),
    direccion_exportador     VARCHAR(500),

    -- Cantidades y valores
    qty1                     DECIMAL(18,3),
    und1                     VARCHAR(20),
    qty2                     DECIMAL(18,3),
    und2                     VARCHAR(20),
    valor_total_usd          DECIMAL(18,2),
    valor_unit1_usd          DECIMAL(18,6),
    valor_unit2_usd          DECIMAL(18,6),

    -- Origen / logística
    pais_origen              VARCHAR(120),
    pais_compra              VARCHAR(120),
    via                      VARCHAR(60),
    descripcion_comercial    TEXT,
    regimen                  TEXT,

    -- Columnas calculadas en la ingesta
    tipo_importacion         VARCHAR(60),
    es_cancun                TINYINT(1) DEFAULT 0,
    costo_unitario_kg        DECIMAL(18,6),
    anio                     SMALLINT,
    mes                      CHAR(7),

    -- Auditoría
    creado_en                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_importador    (importador),
    INDEX idx_exportador    (exportador),
    INDEX idx_partida       (partida_arancelaria),
    INDEX idx_fecha         (fecha),
    INDEX idx_aduana        (aduana),
    INDEX idx_pais_origen   (pais_origen),
    INDEX idx_tipo          (tipo_importacion),
    INDEX idx_cancun        (es_cancun),
    INDEX idx_mes           (mes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Compras por artículo ----------
CREATE TABLE compras_articulos (
    id                       BIGINT AUTO_INCREMENT PRIMARY KEY,

    fecha                    DATE NOT NULL,
    categoria                VARCHAR(120),
    fraccion_arancelaria     VARCHAR(30),
    fraccion_valida          TINYINT(1) NOT NULL DEFAULT 0,
    descripcion              VARCHAR(500) NOT NULL,

    cantidad                 DECIMAL(18,4),
    importe_mxn              DECIMAL(18,2) NOT NULL,
    precio_unitario_mxn      DECIMAL(18,6),
    moneda                   VARCHAR(3) NOT NULL DEFAULT 'MXN',

    proveedor                VARCHAR(255) NOT NULL,
    ambito                   VARCHAR(20) NOT NULL,

    anio                     SMALLINT NOT NULL,
    mes                      CHAR(7) NOT NULL,

    archivo_origen           VARCHAR(255),
    fila_origen              INT,
    creado_en                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_compras_ambito CHECK (ambito IN ('nacional', 'internacional')),
    INDEX idx_compras_fecha      (fecha),
    INDEX idx_compras_categoria  (categoria),
    INDEX idx_compras_fraccion   (fraccion_arancelaria),
    INDEX idx_compras_valida     (fraccion_valida),
    INDEX idx_compras_proveedor  (proveedor),
    INDEX idx_compras_ambito     (ambito),
    INDEX idx_compras_anio       (anio),
    INDEX idx_compras_mes        (mes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Vistas para los reportes ----------
CREATE OR REPLACE VIEW v_importadores AS
SELECT
    importador,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) / NULLIF(SUM(qty1),0)             AS costo_unit_ponderado,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones) AS pct_total
FROM importaciones
GROUP BY importador;

CREATE OR REPLACE VIEW v_importadores_cancun AS
SELECT
    importador,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) / NULLIF(SUM(qty1),0)             AS costo_unit_ponderado,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones WHERE es_cancun = 1) AS pct_total
FROM importaciones
WHERE es_cancun = 1
GROUP BY importador;

CREATE OR REPLACE VIEW v_proveedores AS
SELECT
    exportador,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) / NULLIF(SUM(qty1),0)             AS costo_unit_ponderado,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones) AS pct_total
FROM importaciones
GROUP BY exportador;

CREATE OR REPLACE VIEW v_paises_origen AS
SELECT
    pais_origen,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones) AS pct_total
FROM importaciones
GROUP BY pais_origen;

CREATE OR REPLACE VIEW v_tipo_importacion AS
SELECT
    tipo_importacion,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones) AS pct_total
FROM importaciones
GROUP BY tipo_importacion;

CREATE OR REPLACE VIEW v_partidas AS
SELECT
    partida_arancelaria,
    descripcion_partida,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) / NULLIF(SUM(qty1),0)             AS costo_unit_ponderado,
    SUM(valor_total_usd) * 100.0 / (SELECT SUM(valor_total_usd) FROM importaciones) AS pct_total
FROM importaciones
GROUP BY partida_arancelaria, descripcion_partida;

CREATE OR REPLACE VIEW v_mensual AS
SELECT
    mes,
    SUM(valor_total_usd)                                   AS valor_usd,
    SUM(qty1)                                              AS volumen_kg,
    COUNT(*)                                               AS registros,
    SUM(valor_total_usd) / NULLIF(SUM(qty1),0)             AS costo_unit_ponderado
FROM importaciones
GROUP BY mes
ORDER BY mes;
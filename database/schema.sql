-- MVP Veritrade · esquema MySQL 8 / MariaDB 10.4+
CREATE TABLE IF NOT EXISTS productos (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  nombre    VARCHAR(80) NOT NULL UNIQUE,
  fraccion8 CHAR(8)     NOT NULL,          -- fracción interna (8 dígitos); Veritrade usa 10
  INDEX (fraccion8)                        -- NO única: pechuga y pierna/muslo de pato comparten 02074599
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Un registro por Excel cargado (una fracción + un periodo)
CREATE TABLE IF NOT EXISTS cargas (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  producto_id   INT NOT NULL,
  fraccion10    CHAR(10) NOT NULL,         -- tal como viene en Veritrade
  periodo_ini   DATE NOT NULL,             -- primer día del mes inicial
  periodo_fin   DATE NOT NULL,             -- primer día del mes final
  registros     INT NOT NULL DEFAULT 0,    -- totales de la hoja "Productos"
  fob_usd       DECIMAL(18,2) NOT NULL DEFAULT 0,
  kg            DECIMAL(18,2) NOT NULL DEFAULT 0,
  archivo       VARCHAR(255) NOT NULL,
  fecha_carga   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_carga (producto_id, periodo_ini, periodo_fin),
  FOREIGN KEY (producto_id) REFERENCES productos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Filas de las hojas Importadores, Exportadores, Países Origen, Vías Transporte y Aduanas
CREATE TABLE IF NOT EXISTS detalle (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  carga_id   INT NOT NULL,
  dimension  ENUM('importador','exportador','pais','via','aduana') NOT NULL,
  nombre     VARCHAR(255) NOT NULL,
  registros  INT NOT NULL DEFAULT 0,
  fob_usd    DECIMAL(18,2) NOT NULL DEFAULT 0,
  kg         DECIMAL(18,2) NULL,           -- NULL en aduanas (la columna KG de esa hoja viene corrupta)
  INDEX (carga_id, dimension),
  INDEX (dimension, nombre),
  FOREIGN KEY (carga_id) REFERENCES cargas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Catálogo inicial (tu tabla)
INSERT IGNORE INTO productos (nombre, fraccion8) VALUES
  ('Filete de tilapia',        '03046101'),
  ('Fileta de basa',           '03046201'),
  ('Pulpo',                    '03075201'),
  ('Atún',                     '03048701'),
  ('Calamar',                  '03074302'),
  ('Pato entero',              '02074201'),
  ('Pechuga de pato S/H',      '02074599'),
  ('Pierna y muslo de pato',   '02074599'),
  ('Camarón',                  '03061791');

-- US$/KG no se guarda: se calcula, p. ej.
--   SELECT nombre, SUM(fob_usd)/NULLIF(SUM(kg),0) AS usd_kg FROM detalle WHERE ... GROUP BY nombre;
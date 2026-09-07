BEGIN;

CREATE TABLE IF NOT EXISTS produits (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Routeur',
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT UNIQUE,
    company TEXT,
    email TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_call_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_produits_name ON produits (lower(name));
CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients (phone);

INSERT INTO produits (name, description, category, price_cents, stock) VALUES
  ('Box Fibre Pro 5G', 'Box internet fibre avec modem 5G intégré, WiFi 6, idéale pour particuliers et petites entreprises.', 'Box', 19900, 12),
  ('Routeur WiFi 6 AX3000', 'Routeur WiFi 6 bi-bande AX3000, gestion réseau jusqu''à 40 appareils.', 'Routeur', 8900, 25),
  ('Repeteur WiFi 6', 'Répéteur WiFi 6 Mesh, extension de couverture jusqu''à 120 m².', 'Routeur', 4900, 8),
  ('Modem DOCSIS 3.1', 'Modem câble DOCSIS 3.1, débits jusqu''à 1 Gbit/s.', 'Modem', 7900, 0),
  ('Switch 8 ports Gigabit', 'Switch Ethernet 8 ports Gigabit, plug & play, métal.', 'Accessoire', 3900, 40),
  ('Cable Ethernet 10m Cat6', 'Câble réseau Cat6 10 mètres, connecteurs plaqués or.', 'Accessoire', 1200, 100),
  ('Routeur VPN Pro', 'Routeur VPN sécurisé pour entreprises, 4 ports Gigabit, pare-feu intégré.', 'Routeur', 15900, 6),
  ('Antenne WiFi externe 6dBi', 'Antenne externe pour étendre la portée WiFi, gain 6 dBi.', 'Accessoire', 1500, 3)
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE ON produits, clients TO hotline_app;
GRANT USAGE, SELECT ON SEQUENCE produits_id_seq, clients_id_seq TO hotline_app;

COMMIT;

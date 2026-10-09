-- Optional demo data: a fictional customer and product, so ŠIFRA autofill
-- has something to show on a fresh install. Not meant for a real database.

INSERT INTO customers(name) VALUES
  ('Primer d.o.o., Beograd')
ON CONFLICT (name) DO NOTHING;

INSERT INTO materials(name) VALUES
  ('PE WHITE')
ON CONFLICT (name) DO NOTHING;

INSERT INTO products(sifra, naziv, dimenzija, sirina, customer_id, material_id)
SELECT
  'DEMO-250101',
  'nalepnica Demo sok 0,5 l, P+Z',
  '65 x 140 mm',
  '235 mm',
  (SELECT id FROM customers WHERE name='Primer d.o.o., Beograd'),
  (SELECT id FROM materials WHERE name='PE WHITE')
WHERE NOT EXISTS (SELECT 1 FROM products WHERE sifra='DEMO-250101');

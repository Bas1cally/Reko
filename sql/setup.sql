-- ===========================================
-- ReKo Protokoll - Supabase Setup
-- ===========================================
-- Dieses Script im Supabase SQL Editor ausfuehren
-- Kann mehrfach ausgefuehrt werden (loescht alte Tabellen)

-- Alte Tabellen entfernen (CASCADE loescht auch Policies automatisch)
DROP TABLE IF EXISTS attachments CASCADE;
DROP TABLE IF EXISTS entries CASCADE;
DROP TABLE IF EXISTS attendance CASCADE;
DROP TABLE IF EXISTS protocols CASCADE;
DROP TABLE IF EXISTS participants CASCADE;

-- Alte Funktionen loeschen
DROP FUNCTION IF EXISTS create_weekly_protocol();
DROP FUNCTION IF EXISTS archive_protocol(UUID);

-- 1. Teilnehmer-Tabelle
CREATE TABLE participants (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Protokolle
CREATE TABLE protocols (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  calendar_week INT NOT NULL,
  year INT NOT NULL,
  week_start DATE NOT NULL,
  week_end DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  created_at TIMESTAMPTZ DEFAULT now(),
  archived_at TIMESTAMPTZ
);

-- 3. Anwesenheit
CREATE TABLE attendance (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
  participant_id UUID NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  present BOOLEAN NOT NULL DEFAULT false,
  UNIQUE(protocol_id, participant_id)
);

-- 4. Eintraege (Berichte)
CREATE TABLE entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
  participant_id UUID REFERENCES participants(id),
  author_name TEXT,
  section TEXT NOT NULL DEFAULT 'blitzlicht',
  content TEXT NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Datei-Anhaenge (Metadaten, Dateien in Supabase Storage)
CREATE TABLE attachments (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  entry_id UUID NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  original_name TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  uploaded_at TIMESTAMPTZ DEFAULT now()
);

-- ===========================================
-- Row Level Security (RLS) - offen fuer anon (kein Login noetig)
-- ===========================================
ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE protocols ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance ENABLE ROW LEVEL SECURITY;
ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon read participants" ON participants FOR SELECT TO anon USING (true);
CREATE POLICY "anon insert participants" ON participants FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon update participants" ON participants FOR UPDATE TO anon USING (true);
CREATE POLICY "anon delete participants" ON participants FOR DELETE TO anon USING (true);

CREATE POLICY "anon read protocols" ON protocols FOR SELECT TO anon USING (true);
CREATE POLICY "anon insert protocols" ON protocols FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon update protocols" ON protocols FOR UPDATE TO anon USING (true);

CREATE POLICY "anon read attendance" ON attendance FOR SELECT TO anon USING (true);
CREATE POLICY "anon insert attendance" ON attendance FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon update attendance" ON attendance FOR UPDATE TO anon USING (true);

CREATE POLICY "anon read entries" ON entries FOR SELECT TO anon USING (true);
CREATE POLICY "anon insert entries" ON entries FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon update entries" ON entries FOR UPDATE TO anon USING (true);
CREATE POLICY "anon delete entries" ON entries FOR DELETE TO anon USING (true);

CREATE POLICY "anon read attachments" ON attachments FOR SELECT TO anon USING (true);
CREATE POLICY "anon insert attachments" ON attachments FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon delete attachments" ON attachments FOR DELETE TO anon USING (true);

-- ===========================================
-- HINWEIS: Storage Bucket manuell im Dashboard erstellen!
-- Dashboard -> Storage -> New Bucket -> Name: "attachments" -> Public: AN
-- Dann unter Policies: allow anon for SELECT, INSERT, DELETE
-- ===========================================

-- ===========================================
-- Seed: Teilnehmer (aus Original-Dokument)
-- ===========================================
INSERT INTO participants (name, category, sort_order) VALUES
  -- Aerzte
  ('Dr. Frei, Markus',      'aerzte', 1),
  ('Dr. Schmidt, Sabine',   'aerzte', 2),
  ('Dr. Vitez, Lilla',      'aerzte', 3),
  -- Sozialberatung
  ('Walther, Katja',        'sozialberatung', 10),
  ('Voelkering, Katharina', 'sozialberatung', 11),
  ('Guersel, Helin',        'sozialberatung', 12),
  -- Betriebliche Gesundheitsfoerderung (BGF)
  ('Zieger-Buchta, Katrin', 'bgf', 20),
  ('Mueller-Horn, Susanne', 'bgf', 21),
  ('Krempl, Lara',          'bgf', 22),
  -- WD-Organisation
  ('Schmidt, Emily-Kim',    'wd_orga', 30),
  ('Radimersky, Larissa',   'wd_orga', 31),
  -- Notfall-/Rettungssanitaeter
  ('Putschler, Walter',     'sanitaeter', 40),
  ('Krempl, Elke',          'sanitaeter', 41),
  ('Breig, Bernd',          'sanitaeter', 42),
  ('Kunz, Lia',             'sanitaeter', 43),
  ('Zeller, Tobias',        'sanitaeter', 44),
  ('Jochim, Benjamin',      'sanitaeter', 45),
  ('Siebert, Emanuel',      'sanitaeter', 46),
  ('Wunsch, Fabian',        'sanitaeter', 47),
  ('Goepfrich, Markus',     'sanitaeter', 48),
  -- Betriebsrat
  ('Betriebsratsmitglied',  'betriebsrat', 50);

-- ===========================================
-- Funktion: Neues Protokoll fuer aktuelle KW
-- ===========================================
CREATE OR REPLACE FUNCTION create_weekly_protocol()
RETURNS UUID AS $$
DECLARE
  v_cw INT;
  v_year INT;
  v_week_start DATE;
  v_week_end DATE;
  v_protocol_id UUID;
  v_participant RECORD;
BEGIN
  v_cw := EXTRACT(WEEK FROM CURRENT_DATE)::INT;
  v_year := EXTRACT(YEAR FROM CURRENT_DATE)::INT;

  -- Pruefe ob Protokoll fuer diese KW schon existiert
  SELECT id INTO v_protocol_id FROM protocols
    WHERE calendar_week = v_cw AND year = v_year AND status = 'active';
  IF v_protocol_id IS NOT NULL THEN
    RETURN v_protocol_id;
  END IF;

  -- Montag und Freitag der aktuellen Woche
  v_week_start := date_trunc('week', CURRENT_DATE)::DATE;
  v_week_end := v_week_start + INTERVAL '4 days';

  INSERT INTO protocols (calendar_week, year, week_start, week_end)
    VALUES (v_cw, v_year, v_week_start, v_week_end)
    RETURNING id INTO v_protocol_id;

  -- Anwesenheit fuer alle aktiven Teilnehmer
  FOR v_participant IN SELECT id FROM participants WHERE active = true
  LOOP
    INSERT INTO attendance (protocol_id, participant_id, present)
      VALUES (v_protocol_id, v_participant.id, false);
  END LOOP;

  -- Feste Sektionen anlegen (leer)
  INSERT INTO entries (protocol_id, section, content, sort_order) VALUES
    (v_protocol_id, 'betriebsrat', '', 1),
    (v_protocol_id, 'sonstiges', '', 99);

  RETURN v_protocol_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ===========================================
-- Funktion: Protokoll archivieren
-- ===========================================
CREATE OR REPLACE FUNCTION archive_protocol(p_protocol_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE protocols
    SET status = 'archived', archived_at = now()
    WHERE id = p_protocol_id AND status = 'active';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

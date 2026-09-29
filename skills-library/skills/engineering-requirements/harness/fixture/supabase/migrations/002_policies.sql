ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anon read access" ON public.reports
  FOR SELECT USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;

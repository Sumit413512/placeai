-- Additive provisioning for the restricted production runtime. No existing rows are rewritten.
ALTER TABLE public.student_profiles ADD COLUMN IF NOT EXISTS target_role VARCHAR(160);
ALTER TABLE public.student_profiles ADD COLUMN IF NOT EXISTS role_requirements_json TEXT;
ALTER TABLE public.student_profiles ADD COLUMN IF NOT EXISTS current_semester INTEGER;
ALTER TABLE public.student_profiles ADD COLUMN IF NOT EXISTS enrollment_number VARCHAR(80);
ALTER TABLE public.student_profiles ADD COLUMN IF NOT EXISTS academic_year VARCHAR(40);
ALTER TABLE public.resumes ADD COLUMN IF NOT EXISTS evidence_review_json TEXT;
ALTER TABLE public.student_documents ADD COLUMN IF NOT EXISTS semester INTEGER;
ALTER TABLE public.student_documents ADD COLUMN IF NOT EXISTS label VARCHAR(160);
ALTER TABLE public.student_documents ADD COLUMN IF NOT EXISTS shared_organization_id VARCHAR;
ALTER TABLE public.student_documents ADD COLUMN IF NOT EXISTS shared_at TIMESTAMP;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.student_documents'::regclass AND conname='fk_document_shared_org') THEN
    ALTER TABLE public.student_documents ADD CONSTRAINT fk_document_shared_org FOREIGN KEY (shared_organization_id) REFERENCES public.organizations(id);
  END IF;
END $$;
-- The runtime already has these table grants. A role-specific policy preserves that
-- existing server access while adding RLS defense in depth; no browser role gains access.
DO $$ DECLARE tab TEXT; BEGIN
  FOREACH tab IN ARRAY ARRAY['student_profiles','resumes','student_documents'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=tab AND policyname='placeai_evidence_runtime') THEN
      EXECUTE format('CREATE POLICY placeai_evidence_runtime ON public.%I FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)',tab);
    END IF;
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
  END LOOP;
END $$;


CREATE TABLE IF NOT EXISTS public.technical_practice_attempts (
	id VARCHAR NOT NULL,
	user_id VARCHAR NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	version VARCHAR(40) NOT NULL,
	questions_json TEXT NOT NULL,
	answers_json TEXT NOT NULL,
	result_json TEXT,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	deadline_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_technical_practice_request UNIQUE (user_id, request_id),
	FOREIGN KEY(user_id) REFERENCES public.users (id) ON DELETE CASCADE
)

;
CREATE INDEX IF NOT EXISTS ix_technical_practice_owner ON public.technical_practice_attempts (user_id, created_at);
ALTER TABLE public.technical_practice_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.technical_practice_attempts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.technical_practice_attempts TO placeai_render_runtime;
DROP POLICY IF EXISTS technical_practice_runtime ON public.technical_practice_attempts;
CREATE POLICY technical_practice_runtime ON public.technical_practice_attempts FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);

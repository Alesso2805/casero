CREATE ROLE casero_owner LOGIN BYPASSRLS PASSWORD :'owner_password';
CREATE ROLE casero_backup LOGIN BYPASSRLS PASSWORD :'backup_password';
CREATE ROLE casero_app LOGIN PASSWORD :'app_password';
CREATE ROLE casero_worker LOGIN PASSWORD :'worker_password';
CREATE ROLE casero_admin LOGIN PASSWORD :'admin_password';

ALTER DATABASE :"database" OWNER TO casero_owner;
REVOKE ALL ON DATABASE :"database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database" TO casero_backup, casero_app, casero_worker, casero_admin;

ALTER SCHEMA public OWNER TO casero_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO casero_backup, casero_app, casero_worker, casero_admin;

ALTER DEFAULT PRIVILEGES FOR ROLE casero_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO casero_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE casero_owner
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

// Phase 3: Neo4j ontology bootstrap - idempotent
// Constraints (unique + existence)
CREATE CONSTRAINT asset_id IF NOT EXISTS FOR (n:Asset) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT ip_id IF NOT EXISTS FOR (n:IP) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (n:Domain) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT url_id IF NOT EXISTS FOR (n:URL) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT host_id IF NOT EXISTS FOR (n:Host) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT service_id IF NOT EXISTS FOR (n:Service) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT application_id IF NOT EXISTS FOR (n:Application) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT apiendpoint_id IF NOT EXISTS FOR (n:APIEndpoint) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT vulnerability_id IF NOT EXISTS FOR (n:Vulnerability) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (n:CVE) REQUIRE n.cveId IS UNIQUE;
CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (n:CWE) REQUIRE n.cweId IS UNIQUE;
CREATE CONSTRAINT ttp_id IF NOT EXISTS FOR (n:TTP) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT credential_id IF NOT EXISTS FOR (n:Credential) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT finding_id IF NOT EXISTS FOR (n:Finding) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT remediation_id IF NOT EXISTS FOR (n:Remediation) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT tool_id IF NOT EXISTS FOR (n:Tool) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT report_id IF NOT EXISTS FOR (n:Report) REQUIRE n.id IS UNIQUE;

// Indexes cho traversal nhanh
CREATE INDEX asset_name IF NOT EXISTS FOR (n:Asset) ON (n.name);
CREATE INDEX host_ip IF NOT EXISTS FOR (n:Host) ON (n.ip);
CREATE INDEX vuln_severity IF NOT EXISTS FOR (n:Vulnerability) ON (n.severity);
CREATE INDEX finding_timestamp IF NOT EXISTS FOR (n:Finding) ON (n.timestamp);

// Sample root node (idempotent)
MERGE (root:Asset {id: 'lab-root', name: 'Internal Lab Network'})
RETURN 'Neo4j ontology bootstrap completed';
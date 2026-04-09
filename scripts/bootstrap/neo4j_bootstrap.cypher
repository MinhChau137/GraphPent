
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


CREATE CONSTRAINT weakness_id IF NOT EXISTS FOR (n:Weakness) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (n:CWE) REQUIRE n.cweId IS UNIQUE;
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (n:Category) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT mitigation_id IF NOT EXISTS FOR (n:Mitigation) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT consequence_id IF NOT EXISTS FOR (n:Consequence) REQUIRE n.id IS UNIQUE;


CREATE INDEX asset_name IF NOT EXISTS FOR (n:Asset) ON (n.name);
CREATE INDEX host_ip IF NOT EXISTS FOR (n:Host) ON (n.ip);
CREATE INDEX vuln_severity IF NOT EXISTS FOR (n:Vulnerability) ON (n.severity);
CREATE INDEX cve_id_index IF NOT EXISTS FOR (n:CVE) ON (n.cveId);


CREATE INDEX weakness_name IF NOT EXISTS FOR (n:Weakness) ON (n.name);
CREATE INDEX weakness_abstraction IF NOT EXISTS FOR (n:Weakness) ON (n.abstraction);
CREATE INDEX weakness_cweid IF NOT EXISTS FOR (n:Weakness) ON (n.cweId);
CREATE INDEX category_name IF NOT EXISTS FOR (n:Category) ON (n.name);


MERGE (root:Asset {id: 'lab-root', name: 'Internal Lab Network'})
RETURN 'Neo4j ontology bootstrap completed with CWE support';
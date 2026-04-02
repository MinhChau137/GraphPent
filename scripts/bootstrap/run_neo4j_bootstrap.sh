#!/bin/bash
# Simple wrapper to run Neo4j bootstrap

NEO4J_USER=${1:-neo4j}
NEO4J_PASSWORD=${2:-password123}

cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f /scripts/bootstrap/neo4j_bootstrap.cypher

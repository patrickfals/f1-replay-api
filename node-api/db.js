const path = require("path");
const Database = require("better-sqlite3");

// Reads the same SQLite file the Python API writes to.
const DB_PATH = path.join(__dirname, "..", "f1replay.db");

function getDb() {
  // readonly so it won't accidentally modify data.
  return new Database(DB_PATH, { readonly: true });
}

module.exports = { getDb, DB_PATH };

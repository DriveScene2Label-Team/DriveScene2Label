package com.example.demo.nuscenes.importer;

import com.example.demo.nuscenes.storage.DatasetFiles;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class NuscenesImporter {
 private static final Logger log = LoggerFactory.getLogger(NuscenesImporter.class);
 private final NamedParameterJdbcTemplate jdbc;
 private final ObjectMapper mapper;
 private final DatasetFiles files;
 private final String origin;
 public NuscenesImporter(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper, DatasetFiles files,
   @Value("${nuscenes.data-origin:UNKNOWN}") String origin) {
  this.jdbc = jdbc; this.mapper = mapper; this.files = files;
  this.origin = origin == null ? "UNKNOWN" : origin.strip().toUpperCase(Locale.ROOT);
  if (!Set.of("SYNTHETIC", "NUSCENES", "UNKNOWN").contains(this.origin)) throw new IllegalArgumentException("nuscenes.data-origin must be SYNTHETIC, NUSCENES or UNKNOWN");
 }
 public record ImportResult(long datasetId, Map<String, Integer> sourceCounts, int skippedMapLogLinks) {}

 @Transactional(rollbackFor = Exception.class)
 public ImportResult importDataset(String version) throws IOException {
  return importFrom(files,version,"nuScenes","nuscenes",".",origin);
 }
 @Transactional(rollbackFor = Exception.class)
 public ImportResult importUploaded(DatasetFiles uploaded,String key,String version) throws IOException {
  UUID.fromString(key);
  return importFrom(uploaded,version,"upload-"+key,"uploads",key,"UNKNOWN");
 }
 private ImportResult importFrom(DatasetFiles files,String version,String name,String storage,String root,String dataOrigin) throws IOException {
  if (!version.matches("v[0-9]+\\.[0-9]+-[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid nuScenes version");
  // Keep concurrent imports from interleaving. This lock is released with the transaction.
  long lockStarted=System.nanoTime();
  jdbc.getJdbcTemplate().execute("SELECT pg_advisory_xact_lock(731240921)");
  log.info("[DB_IMPORT] upload={} stage=advisory_lock wall_ms={}",root,(System.nanoTime()-lockStarted)/1_000_000);
  Map<String, JsonNode> sources = new LinkedHashMap<>();
  Map<String, Integer> counts = new LinkedHashMap<>();
  MessageDigest digest;
  try { digest = MessageDigest.getInstance("SHA-256"); }
  catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
  for (var table : ImportSchema.TABLES) {
   byte[] bytes = Files.readAllBytes(files.resolve(version + "/" + table.source() + ".json"));
   digest.update(table.source().getBytes(StandardCharsets.UTF_8)); digest.update(bytes);
   JsonNode rows = mapper.readTree(bytes);
   if (!rows.isArray()) throw new IOException(table.source() + " must be a JSON array");
   sources.put(table.source(), rows); counts.put(table.table(), rows.size());
   if (table.source().equals("sample_data") || table.source().equals("map")) {
    for (JsonNode row : rows) files.resolve(row.path("filename").asText());
   }
  }
  String checksum = HexFormat.of().formatHex(digest.digest());
  var datasetParams = new MapSqlParameterSource().addValue("version", version).addValue("checksum", checksum)
    .addValue("name",name).addValue("storage",storage).addValue("root",root);
  jdbc.update("""
    INSERT INTO dataset(name, version, storage_key, root_relative_path, source_checksum)
    VALUES (:name, :version, :storage, :root, :checksum)
    ON CONFLICT(name, version) DO NOTHING
    """, datasetParams);
  var dataset = jdbc.queryForMap("SELECT id, source_checksum FROM dataset WHERE name = :name AND version = :version", datasetParams);
  if (!checksum.equals(dataset.get("source_checksum"))) throw new IllegalStateException("This dataset version already has different metadata; import under a separate dataset version instead.");
  long datasetId = ((Number) dataset.get("id")).longValue();
  for (var table : ImportSchema.TABLES) {
   long tableStarted=System.nanoTime(),batchNanos=0;int batches=0;
   String columns = "dataset_id, token, raw_payload";
   String values = ":dataset_id, :token, CAST(:raw_payload AS jsonb)";
   for (var field : table.fields()) { columns += ", " + field.column(); values += ", :" + field.column(); }
   String sql = "INSERT INTO " + table.table() + " (" + columns + ") VALUES (" + values + ") ON CONFLICT(dataset_id, token) DO NOTHING";
   List<MapSqlParameterSource> batch = new ArrayList<>();
   Set<String> tokens = new HashSet<>();
   for (JsonNode row : sources.get(table.source())) {
    String token = row.path("token").asText();
    if (token.isBlank() || !tokens.add(token)) throw new IOException("Missing or duplicate token in " + table.source());
    var params = new MapSqlParameterSource("dataset_id", datasetId).addValue("token", token).addValue("raw_payload", row.toString());
    for (var field : table.fields()) params.addValue(field.column(), value(row.at(field.pointer()), field.kind()));
    batch.add(params);
    if (batch.size() == 500) { long before=System.nanoTime();jdbc.batchUpdate(sql, batch.toArray(MapSqlParameterSource[]::new));batchNanos+=System.nanoTime()-before;batches++;batch.clear(); }
   }
   if (!batch.isEmpty()) { long before=System.nanoTime();jdbc.batchUpdate(sql, batch.toArray(MapSqlParameterSource[]::new));batchNanos+=System.nanoTime()-before;batches++; }
   log.info("[DB_IMPORT] dataset={} table={} rows={} batches={} jdbc_ms={} wall_ms={}",datasetId,table.table(),counts.get(table.table()),batches,batchNanos/1_000_000,(System.nanoTime()-tableStarted)/1_000_000);
   log.info("Imported {}: {} records", table.table(), counts.get(table.table()));
  }
  Set<String> logTokens = new HashSet<>();
  for (var row : sources.get("log")) logTokens.add(row.path("token").asText());
  int skipped = 0;
  for (var map : sources.get("map")) for (var token : map.path("log_tokens")) {
   if (!logTokens.contains(token.asText())) { skipped++; continue; }
   jdbc.update("INSERT INTO map_log(dataset_id, map_token, log_token) VALUES (:d, :m, :l) ON CONFLICT DO NOTHING",
     Map.of("d", datasetId, "m", map.path("token").asText(), "l", token.asText()));
  }
  List<MapSqlParameterSource> links = new ArrayList<>();
  for (var annotation : sources.get("sample_annotation")) for (var attribute : annotation.path("attribute_tokens")) {
   links.add(new MapSqlParameterSource("d", datasetId).addValue("a", annotation.path("token").asText()).addValue("t", attribute.asText()));
   if (links.size() == 500) { insertAttributeLinks(links); links.clear(); }
  }
  if (!links.isEmpty()) insertAttributeLinks(links);
  recordProvenance(datasetId, checksum,dataOrigin);
  log.info("nuScenes import complete: dataset={}, skipped map links outside this subset={}", datasetId, skipped);
  return new ImportResult(datasetId, counts, skipped);
 }
 /**
  * Origin comes only from the explicit nuscenes.data-origin setting and is bound to the checksum just verified.
  * Every sample_data/map path was resolved above, so media_validation is PARTIAL (existence, not content).
  * An existing explicit origin is never overwritten; only an UNKNOWN row with the same checksum is upgraded.
  */
 private void recordProvenance(long datasetId, String checksum,String origin) {
  int changed = jdbc.update("""
    INSERT INTO dataset_provenance(dataset_id, origin, metadata_checksum, media_validation, recorded_by, validated_at)
    VALUES (:d, :o, :c, 'PARTIAL', 'importer', now())
    ON CONFLICT(dataset_id) DO UPDATE SET origin = EXCLUDED.origin, recorded_at = now()
    WHERE dataset_provenance.origin = 'UNKNOWN' AND dataset_provenance.metadata_checksum = EXCLUDED.metadata_checksum
    """, new MapSqlParameterSource("d", datasetId).addValue("o", origin).addValue("c", checksum));
  if (changed == 0) log.info("Dataset {} provenance kept as recorded (configured origin {})", datasetId, origin);
 }
 private void insertAttributeLinks(List<MapSqlParameterSource> links) {
  jdbc.batchUpdate("INSERT INTO annotation_attribute(dataset_id, annotation_token, attribute_token) VALUES (:d, :a, :t) ON CONFLICT DO NOTHING", links.toArray(MapSqlParameterSource[]::new));
 }
 private Object value(JsonNode node, ImportSchema.Kind kind) {
  if (node.isMissingNode() || node.isNull() || (node.isTextual() && node.asText().isEmpty())) return null;
  return switch (kind) {
   case TEXT -> node.asText(); case LONG -> node.asLong(); case INT -> node.asInt();
   case DOUBLE -> node.asDouble(); case BOOL -> node.asBoolean();
  };
 }
}

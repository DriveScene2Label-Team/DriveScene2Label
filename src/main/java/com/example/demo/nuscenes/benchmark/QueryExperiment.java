package com.example.demo.nuscenes.benchmark;

import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;
import tools.jackson.databind.json.JsonMapper;

/** Read-only SELECT experiment. No HTTP endpoint, schema changes or shared-stat reset. */
public final class QueryExperiment {
 private static final JsonMapper JSON=JsonMapper.builder().build();
 private static void save(Path root,String name,Object value) throws Exception {
  Files.writeString(root.resolve(name),JSON.writerWithDefaultPrettyPrinter().writeValueAsString(value),StandardOpenOption.CREATE_NEW);
 }
 private static String hash(String value) throws Exception {
  return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
 }
 private static boolean finite(List<Map<String,Object>> rows) {
  return !rows.isEmpty() && rows.stream().allMatch(row->row.values().stream().allMatch(v->!(v instanceof Double d)||Double.isFinite(d)));
 }
 public static void main(String[] args) throws Exception {
  if(args.length<3 || args.length>4) throw new IllegalArgumentException("Usage: dataset-id original-search-sql fresh-output-directory [plan-mode]");
  String planMode=args.length==4?args[3]:"auto";
  if(!Set.of("auto","force_custom_plan","force_generic_plan","paired_custom").contains(planMode))throw new IllegalArgumentException("Unsupported plan mode");
  long dataset=Long.parseLong(args[0]);if(dataset<=0)throw new IllegalArgumentException("Expected positive dataset ID");
  String original=Files.readString(Path.of(args[1]));
  // Input must be the repository's SELECT CTE, never arbitrary write statements.
  if(!original.stripLeading().startsWith("WITH distances AS (") || original.contains(";") || !original.contains("LIMIT :k"))
   throw new IllegalArgumentException("Expected unchanged SceneSearchRepository SELECT text block");
  String materialized=original.replaceFirst("WITH distances AS \\(","WITH distances AS MATERIALIZED (");
  Path root=Path.of(args[2]);Files.createDirectory(root);
  String model=System.getenv().getOrDefault("EMBEDDING_MODEL_NAME","ViT-L-14-quickgelu/openai");
  String preprocess=System.getenv().getOrDefault("EMBEDDING_PREPROCESS","lr-square-crop-mean");
  Map<String,Object> manifest=new LinkedHashMap<>();
  manifest.put("started_at",Instant.now().toString());manifest.put("dataset",dataset);
  manifest.put("plan_cache_mode",planMode);
  manifest.put("scope","existing RDS; read-only exact search; three stored image vectors as query fixtures, not text inference or end-to-end API timing");
  manifest.put("baseline_sql_sha256",hash(original));manifest.put("materialized_sql_sha256",hash(materialized));
  manifest.put("candidate","materialize distance CTE to avoid repeated cosine calculations; may add temp I/O");
  manifest.put("quality_gate","all ordered SQL result fields equal for dataset/global and MAX/AVERAGE/TOP_K_AVERAGE");
  Class.forName("org.postgresql.Driver");
  try(Connection connection=DriverManager.getConnection(System.getenv("DB_URL"),System.getenv("DB_USERNAME"),System.getenv("DB_PASSWORD"))) {
   connection.setReadOnly(true);connection.setAutoCommit(false);
   try(Statement statement=connection.createStatement()) {
    statement.execute("SET LOCAL statement_timeout='30s'");statement.execute("SET LOCAL lock_timeout='2s'");
    statement.execute("SET LOCAL plan_cache_mode='"+(planMode.equals("paired_custom")?"auto":planMode)+"'");
   }
   var jdbc=new NamedParameterJdbcTemplate(new SingleConnectionDataSource(connection,true));
   Map<String,Object> common=new HashMap<>();common.put("model",model);common.put("preprocess",preprocess);
   common.put("dataset",dataset);common.put("k",10);common.put("imageTopK",3);common.put("keyframesOnly",true);
   var vectors=jdbc.queryForList("SELECT sample_data_token,embedding::text AS embedding FROM image_embedding WHERE dataset_id=:dataset AND model_name=:model AND preprocess=:preprocess ORDER BY sample_data_token LIMIT 3",common);
   if(vectors.size()!=3)throw new IllegalStateException("Need three existing image-vector fixtures");
   manifest.put("server",jdbc.queryForList("SELECT version() AS version,current_setting('work_mem') AS work_mem,current_setting('jit') AS jit,current_setting('max_parallel_workers_per_gather') AS parallel_workers",Map.of()));
   manifest.put("extensions",jdbc.queryForList("SELECT extname,extversion FROM pg_extension WHERE extname='vector'",Map.of()));
   manifest.put("row_counts",jdbc.queryForList("SELECT dataset_id,count(*) AS images FROM image_embedding GROUP BY dataset_id ORDER BY dataset_id",Map.of()));
   save(root,"manifest.json",manifest);
   save(root,"indexes.json",jdbc.queryForList("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN ('image_embedding','sample_data','sample','scene','sensor','calibrated_sensor') ORDER BY tablename,indexname",Map.of()));
   List<Map<String,Object>> runs=new ArrayList<>();List<Map<String,Object>> checks=new ArrayList<>();
   for(int query=0;query<vectors.size();query++) {
    var fixture=vectors.get(query);String vector=(String)fixture.get("embedding");
    for(boolean filtered:new boolean[]{true,false})for(String aggregation:List.of("MAX","AVERAGE","TOP_K_AVERAGE")) {
     String name="q"+query+"-"+(filtered?"dataset":"global")+"-"+aggregation;
     Map<String,Object> parameters=new HashMap<>(common);parameters.put("dataset",filtered?dataset:null);
     parameters.put("vector",vector);parameters.put("aggregation",aggregation);
     // Warm both SQL paths separately before timing. No query output or vector is logged here.
     for(String mode:List.of("baseline","materialized")) {
      configurePlan(connection,planMode,mode);
      jdbc.queryForList(mode.equals("baseline")?original:materialized,parameters);
     }
     for(int repeat=0;repeat<3;repeat++) {
      Map<String,List<Map<String,Object>>> outputs=new HashMap<>();
      for(String mode:(repeat%2==0?List.of("baseline","materialized"):List.of("materialized","baseline"))) {
       String sql=mode.equals("baseline")?original:materialized;
       // Reset to production auto outside baseline timing; include the candidate SET round trip.
       if(planMode.equals("paired_custom") && mode.equals("baseline"))configurePlan(connection,planMode,mode);
       long start=System.nanoTime();
       if(planMode.equals("paired_custom") && mode.equals("materialized"))configurePlan(connection,planMode,mode);
       var rows=jdbc.queryForList(sql,parameters);double seconds=(System.nanoTime()-start)/1e9;
       if(!finite(rows))throw new IllegalStateException("Empty or nonfinite search fixture");
       outputs.put(mode,rows);
       Map<String,Object> run=new LinkedHashMap<>();run.put("scenario",name);run.put("repeat",repeat);run.put("mode",mode);
       run.put("client_seconds",seconds);run.put("rows",rows.size());run.put("fixture_token",fixture.get("sample_data_token"));run.put("vector_sha256",hash(vector));
       runs.add(run);save(root,name+"-r"+repeat+"-"+mode+"-result.json",rows);
      }
      checks.add(Map.of("scenario",name,"repeat",repeat,"exact_ordered_rows",outputs.get("baseline").equals(outputs.get("materialized"))));
     }
     for(String mode:List.of("baseline","materialized")) {
      configurePlan(connection,planMode,mode);
      String sql=mode.equals("baseline")?original:materialized;
      String plan=jdbc.query("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON,TIMING OFF) "+sql,parameters,(rs,n)->rs.getString(1)).getFirst();
      // The full plan may contain the vector constant: retain it locally, not in Git.
      Files.writeString(root.resolve(name+"-"+mode+"-plan.json"),plan,StandardOpenOption.CREATE_NEW);
     }
     // Counters belong to this session only. No SQL text or query vector is exported.
     save(root,name+"-prepared-statements.json",jdbc.queryForList("SELECT name,md5(statement) AS statement_hash,parameter_types::text AS parameter_types,generic_plans,custom_plans FROM pg_prepared_statements ORDER BY name",Map.of()));
     System.out.println("Completed query scenario "+name+" with three paired repeats.");
    }
   }
   save(root,"runs.json",runs);save(root,"quality-checks.json",checks);
   save(root,"completion.json",Map.of("finished_at",Instant.now().toString(),"runs",runs.size(),"pairs",checks.size(),
    "exact_results",checks.stream().allMatch(c->Boolean.TRUE.equals(c.get("exact_ordered_rows")))));
   connection.rollback();
  } catch(SQLException failure) {
   save(root,"failure.json",Map.of("type",failure.getClass().getSimpleName(),"sqlstate",Objects.toString(failure.getSQLState(),"unknown")));
   throw new IllegalStateException("Read-only query experiment failed; SQL state retained without connection details.");
  }
 }
 private static void configurePlan(Connection connection,String planMode,String mode) throws SQLException {
  if(!planMode.equals("paired_custom"))return;
  try(Statement statement=connection.createStatement()) {
   statement.execute("SET LOCAL plan_cache_mode='"+(mode.equals("baseline")?"auto":"force_custom_plan")+"'");
  }
 }
}

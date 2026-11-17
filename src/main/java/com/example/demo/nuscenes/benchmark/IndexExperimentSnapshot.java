package com.example.demo.nuscenes.benchmark;

import java.nio.file.*;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import tools.jackson.databind.json.JsonMapper;

/** Read-only local experiment utility. Not an HTTP endpoint; credentials never leave the process. */
public final class IndexExperimentSnapshot {
 private static String setting(String name,String fallback) { return System.getenv().getOrDefault(name,fallback); }
 public static void main(String[] args) throws Exception {
  if(args.length<2 || args.length>3 || (args.length==3 && !"--stats-only".equals(args[2]))) throw new IllegalArgumentException("Usage: dataset-id output-json [--stats-only]");
  boolean statsOnly=args.length==3;
  long dataset=Long.parseLong(args[0]); if(dataset<=0 && !statsOnly) throw new IllegalArgumentException("Invalid dataset");
  Path output=Path.of(args[1]); if(Files.exists(output)) throw new IllegalArgumentException("Use a fresh output file");
  String model=setting("EMBEDDING_MODEL_NAME","ViT-L-14-quickgelu/openai");
  String preprocess=setting("EMBEDDING_PREPROCESS","lr-square-crop-mean");
  Map<String,Object> result=new LinkedHashMap<>();result.put("at",Instant.now().toString());result.put("dataset",dataset);
  result.put("model",model);result.put("preprocess",preprocess);
  Class.forName("org.postgresql.Driver");
  try(Connection connection=DriverManager.getConnection(System.getenv("DB_URL"),System.getenv("DB_USERNAME"),System.getenv("DB_PASSWORD"))) {
   connection.setReadOnly(true);
   List<Map<String,Object>> vectors=new ArrayList<>();
   long started=System.nanoTime();
   if(!statsOnly) try(PreparedStatement query=connection.prepareStatement("SELECT sample_data_token,embedding::text FROM image_embedding WHERE dataset_id=? AND model_name=? AND preprocess=? ORDER BY sample_data_token")) {
    query.setLong(1,dataset);query.setString(2,model);query.setString(3,preprocess);
    try(ResultSet rows=query.executeQuery()) { while(rows.next()) vectors.add(Map.of("sample_data_token",rows.getString(1),"embedding",rows.getString(2))); }
   }
   result.put("vectors",vectors);result.put("count",vectors.size());result.put("export_ms",(System.nanoTime()-started)/1_000_000);
   try(Statement query=connection.createStatement();ResultSet rows=query.executeQuery("""
    SELECT queryid,calls,total_exec_time,rows,
      CASE WHEN query ILIKE '%INSERT INTO image_embedding%' THEN 'vector_insert'
       WHEN query ILIKE '%SELECT EXISTS%image_embedding%' THEN 'vector_exists'
       WHEN query ILIKE '%e.sample_data_token IS NULL%' THEN 'pending_batch'
       WHEN query ILIKE '%SELECT sd.dataset_id,sd.token,sd.relative_path,s.modality,d.storage_key,d.root_relative_path%' THEN 'source_lookup'
       ELSE 'other_embedding_or_source_query' END AS kind
    FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
     AND (query ILIKE '%image_embedding%' OR query ILIKE '%sample_data%')
     AND query NOT ILIKE '%pg_stat_statements%'
    """)) {
    List<Map<String,Object>> stats=new ArrayList<>();
    while(rows.next()) stats.add(Map.of("queryid",rows.getLong(1),"calls",rows.getLong(2),"total_exec_time_ms",rows.getDouble(3),"rows",rows.getLong(4),"kind",rows.getString(5)));
    result.put("pg_stat_statements",stats);
   } catch(SQLException unavailable) {
    result.put("pg_stat_statements_unavailable_sqlstate",Objects.toString(unavailable.getSQLState(),"unknown"));
   }
  } catch(SQLException failure) {
   // Do not print connection strings, environment variables or arbitrary database messages.
   result.put("error_type",failure.getClass().getSimpleName());result.put("sqlstate",Objects.toString(failure.getSQLState(),"unknown"));
   Files.writeString(output,JsonMapper.builder().build().writerWithDefaultPrettyPrinter().writeValueAsString(result),StandardOpenOption.CREATE_NEW);
   throw new IllegalStateException("Read-only snapshot failed; SQL state saved in output.");
  }
  Files.writeString(output,JsonMapper.builder().build().writerWithDefaultPrettyPrinter().writeValueAsString(result),StandardOpenOption.CREATE_NEW);
  System.out.println("Snapshot completed: "+result.get("count")+" vectors; no database mutations.");
 }
}

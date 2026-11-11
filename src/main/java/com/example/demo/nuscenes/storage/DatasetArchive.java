package com.example.demo.nuscenes.storage;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.apache.commons.compress.archivers.tar.TarConstants;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Streaming extraction of regular files only. Archive bytes, not the extension, identify the format. */
public final class DatasetArchive {
 private DatasetArchive() {}
 public enum Format {
  ZIP(".zip","application/zip"), TGZ(".tar.gz","application/gzip");
  public final String extension,contentType;
  Format(String extension,String contentType) { this.extension=extension;this.contentType=contentType; }
 }
 public static boolean supported(String name) {
  if(name==null) return false;
  String lower=name.toLowerCase(Locale.ROOT);
  return lower.endsWith(".zip") || lower.endsWith(".tgz") || lower.endsWith(".tar.gz");
 }
 public static Format detect(Path path) throws IOException {
  try(var input=Files.newInputStream(path)) {
   byte[] head=input.readNBytes(4);
   if(head.length>=2 && (head[0]&255)==31 && (head[1]&255)==139) return Format.TGZ;
   if(head.length==4 && head[0]=='P' && head[1]=='K' && ((head[2]==3 && head[3]==4)||(head[2]==5 && head[3]==6))) return Format.ZIP;
  }
  throw bad("ZIP 또는 TGZ 형식이 아닙니다. 확장자만 변경하지 말고 원본 압축 파일을 선택해 주세요.",null);
 }
 public static void extract(Path archive,Path root,long limit) throws IOException {
  root=root.toAbsolutePath().normalize();
  try {
   if(detect(archive)==Format.ZIP) extractZip(archive,root,limit);
   else extractTar(archive,root,limit);
  } catch(ZipException|EOFException error) {
   throw bad("압축 파일이 손상되었거나 끝까지 저장되지 않았습니다. 다운로드·압축 작업이 끝난 원본 파일을 다시 선택해 주세요.",error);
  }
 }
 private static void extractZip(Path archive,Path root,long limit) throws IOException {
  // ZipInputStream alone accepts some archives without the final directory. Reject truncated uploads first.
  try(var directory=new ZipFile(archive.toFile())) {
   if(directory.size()==0 || directory.size()>100000) throw bad("압축 파일 항목 수가 올바르지 않습니다.",null);
  }
  long total=0;int entries=0;
  try(var zip=new ZipInputStream(Files.newInputStream(archive))) {
   for(var entry=zip.getNextEntry();entry!=null;entry=zip.getNextEntry()) {
    if(++entries>100000) throw bad("압축 파일 항목 수 제한을 초과했습니다.",null);
    Path target=target(root,entry.getName(),entry.isDirectory());
    if(entry.isDirectory()) { Files.createDirectories(target);continue; }
    total=copy(zip,target,total,limit);
   }
  }
 }
 private static void extractTar(Path archive,Path root,long limit) throws IOException {
  long total=0;int entries=0;
  try(var gzip=new GZIPInputStream(Files.newInputStream(archive));var tar=new TarArchiveInputStream(gzip)) {
   for(var entry=tar.getNextEntry();entry!=null;entry=tar.getNextEntry()) {
    byte type=entry.getLinkFlag();
    if(++entries>100000 || !entry.isCheckSumOK() || entry.isSparse() || (type!=TarConstants.LF_NORMAL && type!=TarConstants.LF_OLDNORM && type!=TarConstants.LF_DIR))
     throw bad("TGZ에는 일반 파일과 폴더만 넣을 수 있습니다. 링크·특수 파일 또는 잘못된 헤더가 있습니다.",null);
    Path target=target(root,entry.getName(),entry.isDirectory());
    if(entry.isDirectory()) { Files.createDirectories(target);continue; }
    if(entry.getSize()>limit-total) throw tooLarge();
    total=copy(tar,target,total,limit);
   }
   if(entries==0) throw bad("유효한 TAR.GZ 압축 파일이 아닙니다.",null);
   // Consume gzip footer to verify CRC even when TAR ends before the gzip member does.
   byte[] buffer=new byte[65536];long padding=0;int count;
   while((count=gzip.read(buffer))!=-1) { padding+=count;if(padding>16L*1024*1024) throw bad("TGZ 끝부분의 추가 데이터가 너무 큽니다.",null); }
  }
 }
 private static Path target(Path root,String name,boolean directory) {
  if(name==null || name.isBlank() || name.startsWith("/") || name.contains("\\") || name.contains(":") || Arrays.asList(name.split("/")).contains(".."))
   throw bad("압축 파일 안에 허용되지 않는 경로가 있습니다.",null);
  Path target=root.resolve(name).normalize();
  if(!target.startsWith(root) || (target.equals(root) && !directory)) throw bad("압축 파일 경로가 데이터 폴더를 벗어납니다.",null);
  return target;
 }
 private static long copy(InputStream input,Path target,long total,long limit) throws IOException {
  Files.createDirectories(target.getParent());
  try(var output=Files.newOutputStream(target,StandardOpenOption.CREATE_NEW)) {
   byte[] buffer=new byte[65536];int count;
   while((count=input.read(buffer))!=-1) { total+=count;if(total>limit) throw tooLarge();output.write(buffer,0,count); }
  }
  return total;
 }
 private static ResponseStatusException bad(String message,Throwable cause) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message,cause); }
 private static ResponseStatusException tooLarge() { return new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"압축 해제 용량 제한을 초과했습니다."); }
}

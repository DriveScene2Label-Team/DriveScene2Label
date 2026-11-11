package com.example.demo;
import com.example.demo.nuscenes.storage.DatasetArchive;
import java.io.*;
import java.nio.file.*;
import java.util.zip.*;
import org.apache.commons.compress.archivers.tar.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;

class DatasetArchiveTests {
 @TempDir Path root;
 static byte[] tgz(String name,byte[] content,byte type) throws IOException {
  var bytes=new ByteArrayOutputStream();
  try(var gzip=new GZIPOutputStream(bytes);var tar=new TarArchiveOutputStream(gzip)) {
   tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX);
   tar.putArchiveEntry(new TarArchiveEntry("./",TarConstants.LF_DIR));tar.closeArchiveEntry();
   var entry=new TarArchiveEntry(name,type);
   if(type==TarConstants.LF_NORMAL) entry.setSize(content.length); else entry.setLinkName("../outside");
   tar.putArchiveEntry(entry);if(type==TarConstants.LF_NORMAL) tar.write(content);tar.closeArchiveEntry();
  }
  return bytes.toByteArray();
 }
 @Test void tgzSupportsDotRootAndPaxNames() throws Exception {
  String name="./samples/"+"x".repeat(120)+".jpg";
  Path archive=root.resolve("mini.tgz");Files.write(archive,tgz(name,"camera".getBytes(),TarConstants.LF_NORMAL));
  DatasetArchive.extract(archive,root.resolve("out"),1024);
  assertThat(Files.readString(root.resolve("out").resolve(name))).isEqualTo("camera");
 }
 @Test void tarRejectsLinksTraversalAndExpandedLimit() throws Exception {
  for(byte type:new byte[]{TarConstants.LF_SYMLINK,TarConstants.LF_LINK,TarConstants.LF_FIFO}) {
   Path archive=root.resolve("bad-"+type+".tgz");Files.write(archive,tgz("samples/file",new byte[0],type));
   assertThatThrownBy(()->DatasetArchive.extract(archive,root.resolve("out-"+type),100)).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  }
  Path escape=root.resolve("escape.tgz");Files.write(escape,tgz("../outside",new byte[]{1},TarConstants.LF_NORMAL));
  assertThatThrownBy(()->DatasetArchive.extract(escape,root.resolve("out-escape"),100)).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  Path big=root.resolve("big.tgz");Files.write(big,tgz("file",new byte[101],TarConstants.LF_NORMAL));
  assertThatThrownBy(()->DatasetArchive.extract(big,root.resolve("out-big"),100)).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  assertThat(Files.exists(root.resolve("outside"))).isFalse();
 }
 @Test void rejectsMissingZipDirectoryAndGzipFooterWithSpecificReason() throws Exception {
  var bytes=new ByteArrayOutputStream();
  try(var zip=new ZipOutputStream(bytes)) { zip.putNextEntry(new ZipEntry("file"));zip.write(1);zip.closeEntry(); }
  Path zip=root.resolve("broken.zip");Files.write(zip,java.util.Arrays.copyOf(bytes.toByteArray(),bytes.size()-22));
  assertThatThrownBy(()->DatasetArchive.extract(zip,root.resolve("out-zip"),100)).hasMessageContaining("손상");
  byte[] compressed=tgz("file",new byte[]{1},TarConstants.LF_NORMAL);
  Path tgz=root.resolve("broken.tgz");Files.write(tgz,java.util.Arrays.copyOf(compressed,compressed.length-8));
  assertThatThrownBy(()->DatasetArchive.extract(tgz,root.resolve("out-tgz"),100)).hasMessageContaining("손상");
 }
}

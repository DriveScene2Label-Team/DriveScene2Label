package com.example.demo;

import com.example.demo.nuscenes.storage.*;
import java.io.*;
import java.nio.file.*;
import java.util.UUID;
import java.util.zip.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class UploadStorageTests {
 @TempDir Path root;
 @Test void anotherServerRestoresOriginalAndMediaFromDurableArchive() throws Exception {
  var remote=mock(UploadArchiveStore.class);
  String key=UUID.randomUUID().toString();
  doAnswer(call->{
   try(var zip=new ZipOutputStream(Files.newOutputStream(call.getArgument(1,Path.class)))) {
    zip.putNextEntry(new ZipEntry("samples/front.jpg"));zip.write("image-data".getBytes());zip.closeEntry();
   }
   return null;
  }).when(remote).fetch(eq(key),any(Path.class));
  var storage=new DatasetStorage(new DatasetFiles(root.resolve("base").toString()),root.toString(),remote,1024);
  assertThat(Files.readString(storage.files("uploads",key).resolve("samples/front.jpg"))).isEqualTo("image-data");
  assertThat(Files.isRegularFile(storage.archive(key))).isTrue();
  storage.files("uploads",key);
  verify(remote,times(1)).fetch(eq(key),any(Path.class));
 }
 @Test void failedArchiveIsNotPublishedAsDataset() throws Exception {
  var remote=mock(UploadArchiveStore.class);String key=UUID.randomUUID().toString();
  doAnswer(call->{
   try(var zip=new ZipOutputStream(Files.newOutputStream(call.getArgument(1,Path.class)))) {
    zip.putNextEntry(new ZipEntry("../outside"));zip.write(1);zip.closeEntry();
   }
   return null;
  }).when(remote).fetch(eq(key),any(Path.class));
  var storage=new DatasetStorage(new DatasetFiles(root.toString()),root.toString(),remote,1024);
  assertThatThrownBy(()->storage.files("uploads",key)).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  assertThat(Files.exists(root.resolve("datasets").resolve(key))).isFalse();
  assertThatThrownBy(()->storage.archive("../escape")).isInstanceOf(IOException.class);
 }
}

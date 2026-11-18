package com.example.demo.nuscenes.dto;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
/** POST /embedding/images. results[i] answers image_paths[i]; exactly one of embedding/error is set. */
public record ImageBatchEmbeddingResponse(@JsonProperty("model_name") String modelName, int dimension, String preprocess, List<Item> results) {
 public record Item(@JsonProperty("image_path") String imagePath, List<Double> embedding, Error error) {}
 public record Error(int status, String code, String message) {}
}

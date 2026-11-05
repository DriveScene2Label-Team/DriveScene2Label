package com.example.demo.nuscenes.service;
import java.util.*;
/**
 * Class names used by label edits.
 * GT keeps its original nuScenes category; its display class is the VESPA 8class comparison class of that category
 * (VESPA assets/class_mapping/8class.yaml, the same table as frontend/src/lib/classes.ts) or, for a category that
 * VESPA does not evaluate, the category name itself. Never coerced to "vehicle".
 */
public final class LabelClasses {
 private LabelClasses() {}
 /** Classes a box can be renamed to (VESPA 8class names plus the 1/3class generic "vehicle"). */
 public static final List<String> LABELS=List.of("car","truck","bus","trailer","construction_vehicle","pedestrian","motorcycle","bicycle","vehicle");
 private static final Map<String,String> NUSC_8=Map.ofEntries(
  Map.entry("human.pedestrian.adult","pedestrian"),Map.entry("human.pedestrian.child","pedestrian"),
  Map.entry("human.pedestrian.construction_worker","pedestrian"),Map.entry("human.pedestrian.police_officer","pedestrian"),
  Map.entry("vehicle.bicycle","bicycle"),Map.entry("vehicle.bus.bendy","bus"),Map.entry("vehicle.bus.rigid","bus"),Map.entry("vehicle.car","car"),
  Map.entry("vehicle.construction","construction_vehicle"),Map.entry("vehicle.motorcycle","motorcycle"),Map.entry("vehicle.trailer","trailer"),Map.entry("vehicle.truck","truck"));
 /** Display class of an original GT category. */
 public static String gtBase(String categoryName) {
  if(categoryName==null || categoryName.isBlank()) return "unknown";
  return NUSC_8.getOrDefault(categoryName,categoryName);
 }
}

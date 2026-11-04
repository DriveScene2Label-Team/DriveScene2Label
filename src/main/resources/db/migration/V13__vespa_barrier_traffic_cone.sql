-- VESPA patch 0001 (ai-server/vespa-patches) adds barrier and traffic_cone to the 8class mapping.
-- V4 is not edited: replace its inline detection_name check with the extended list.
ALTER TABLE predicted_annotation DROP CONSTRAINT predicted_annotation_detection_name_check;
ALTER TABLE predicted_annotation ADD CONSTRAINT predicted_annotation_detection_name_check
 CHECK (detection_name IN ('vehicle','car','truck','bus','trailer','construction_vehicle','pedestrian','motorcycle','bicycle',
                           'barrier','traffic_cone'));

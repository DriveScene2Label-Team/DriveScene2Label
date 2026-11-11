package com.example.demo;

import com.example.demo.nuscenes.service.MatchScoreCalibration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class MatchScoreCalibrationTests {
 static final String MODEL="ViT-L-14-quickgelu/openai", PRE="lr-square-crop-mean";
 final MatchScoreCalibration cal=new MatchScoreCalibration(MODEL,PRE,0.174,0.259,0.179,0.261,0.134,0.205);

 @Test void linearBetweenAnchorsAndClamped() {
  assertThat(cal.matchScore(MODEL,PRE,"TOP_K_AVERAGE",0.174)).isZero();
  assertThat(cal.matchScore(MODEL,PRE,"TOP_K_AVERAGE",0.259)).isEqualTo(100);
  assertThat(cal.matchScore(MODEL,PRE,"TOP_K_AVERAGE",0.2165)).isEqualTo(50);
  assertThat(cal.matchScore(MODEL,PRE,"TOP_K_AVERAGE",0.10)).isZero();    // unrelated text
  assertThat(cal.matchScore(MODEL,PRE,"TOP_K_AVERAGE",0.30)).isEqualTo(100);
 }
 @Test void eachAggregationHasItsOwnAnchors() {
  assertThat(cal.matchScore(MODEL,PRE,"max",0.261)).isEqualTo(100);
  assertThat(cal.matchScore(MODEL,PRE,"AVERAGE",0.205)).isEqualTo(100);
  assertThat(cal.matchScore(MODEL,PRE,"AVERAGE",0.134)).isZero();
  assertThat(cal.matchScore(MODEL,PRE,"UNKNOWN",0.25)).isNull();
 }
 @Test void otherEmbeddingGetsNoScore() {
  assertThat(cal.matchScore("ViT-B-32/openai",PRE,"MAX",0.25)).isNull();
  assertThat(cal.matchScore(MODEL,"center-crop","MAX",0.25)).isNull();
  assertThat(cal.matchScore(MODEL,PRE,"MAX",Double.NaN)).isNull();
 }
 @Test void invertedAnchorsFailAtStartup() {
  assertThatThrownBy(()->new MatchScoreCalibration(MODEL,PRE,0.3,0.2,0.1,0.2,0.1,0.2)).isInstanceOf(IllegalStateException.class);
 }
}

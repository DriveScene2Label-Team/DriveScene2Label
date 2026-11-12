/**
 * Job / recording terminal errorCode → what happened and what to do. Codes come from the server (V6+); rows without a
 * code keep their free-text message and get the generic guidance. Nothing here guesses a cause from a message.
 */
export interface ErrorGuide {
  title: string;
  action: string;
  /** Re-running the same work is reasonable only after the environment is fixed. */
  environment: boolean;
}

const G: Record<string, ErrorGuide> = {
  AI_ENDPOINT_UNSUPPORTED: { title: '연결된 AI 서버가 이 기능을 제공하지 않아요', action: 'AI 서버 구성을 확인하세요. 같은 환경에서 다시 실행해도 같은 결과예요.', environment: true },
  AI_UNREACHABLE: { title: 'AI 서버에 연결하지 못했어요', action: 'AI 서버 실행 상태와 주소를 확인한 뒤 다시 실행하세요.', environment: true },
  AI_TIMEOUT: { title: 'AI 서버 응답 시간이 초과됐어요', action: 'AI 서버에서 작업이 계속 실행 중일 수 있어요. 실행 로그를 먼저 확인하세요.', environment: true },
  AI_HTTP_ERROR: { title: 'AI 서버가 오류를 반환했어요', action: 'AI 서버 로그를 확인하세요.', environment: true },
  VESPA_NOT_CONFIGURED: { title: 'VESPA 실행 환경이 설정되지 않았어요', action: '실행 환경을 준비한 뒤 다시 실행하세요.', environment: true },
  VESPA_DATA_NOT_READY: { title: 'AI 서버의 데이터셋 메타데이터를 읽지 못했어요', action: '데이터셋 경로와 버전을 확인하세요.', environment: true },
  VESPA_LAUNCH_FAILED: { title: 'VESPA 실행을 시작하지 못했어요', action: '실행 환경(원격 포함)을 확인하세요.', environment: true },
  VESPA_REMOTE_UNREACHABLE: { title: '원격 클러스터와 연결이 끊겼어요', action: '원격 작업이 남아 있을 수 있어요. 클러스터 상태를 확인한 뒤 결정하세요.', environment: true },
  USER_CANCELLED: { title: '사용자 요청으로 중단했어요', action: '자동으로 다시 실행하지 않아요. 필요할 때 직접 새 작업을 시작하세요.', environment: false },
  VESPA_BUSY: { title: 'AI 서버가 다른 VESPA 작업을 실행 중이었어요', action: '진행 중인 작업이 끝난 뒤 다시 실행하세요.', environment: false },
  VESPA_EXECUTION_FAILED: { title: 'VESPA 실행이 실패했어요', action: 'AI 서버 실행 로그를 확인하세요.', environment: false },
  VESPA_INVALID_RESULT: { title: 'VESPA 결과가 없거나 형식이 올바르지 않아요', action: '실행 로그와 결과 파일을 확인하세요.', environment: false },
  VESPA_TIMEOUT: { title: 'VESPA 실행 시간 상한을 넘었어요', action: '시간 상한과 자원을 확인하세요.', environment: false },
  SCENE_NOT_FOUND: { title: 'AI 서버 데이터셋에 이 씬이 없어요', action: 'Spring과 AI 서버가 같은 데이터셋을 쓰는지 확인하세요.', environment: true },
  RESULT_VALIDATION_FAILED: { title: 'AI 결과가 요청과 맞지 않아 저장하지 않았어요', action: '결과 파일과 실행 로그를 확인하세요.', environment: false },
  RESULT_STORAGE_FAILED: { title: '결과를 저장하지 못했어요', action: '다시 추론하지 말고 저장소(DB) 문제를 먼저 확인하세요.', environment: true },
  RECORDING_FILE_MISSING: { title: '준비됐던 recording 파일이 서버에 없어요', action: 'recording만 다시 만들면 돼요.', environment: false },
};

export function errorGuide(code: string | null | undefined): ErrorGuide | null {
  return code ? G[code] ?? null : null;
}

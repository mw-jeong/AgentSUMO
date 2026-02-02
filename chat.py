#!/usr/bin/env python3
"""
AgentSUMO CLI 대화 인터페이스

직접 AgentSUMO와 대화할 수 있습니다.
"""

import asyncio
import sys
import argparse
import os
from pathlib import Path
from agentsumo import AgentSUMO

# Load API key from claude_api.txt or .env
api_key_file = Path(__file__).parent / "claude_api.txt"
env_file = Path(__file__).parent / ".env"

if api_key_file.exists():
    with open(api_key_file) as f:
        api_key = f.read().strip()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
elif env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value


async def main(debug=False):
    """
    CLI 대화 시작
    
    Args:
        debug: Debug 모드 (Claude raw response 표시)
    """
    print("\n" + "="*70)
    print("🤖 AgentSUMO - AI-Powered SUMO Simulation Platform")
    if debug:
        print("    🐛 DEBUG MODE: Raw responses visible")
    print("="*70)
    print("\n초기화 중...")
    
    try:
        async with AgentSUMO(enable_debug=debug) as agent:
            print("\n✅ AgentSUMO 준비 완료!")
            print("\n명령어:")
            print("  - 'quit' 또는 'exit': 종료")
            print("  - 'state': 현재 상태 확인")
            print("  - 'reset': 대화 이력 리셋")
            print("  - 'help': 도움말")
            print("\n💡 Tip:")
            print("  - <thinking> 태그: Claude의 추론 과정 (Complex tasks)")
            print("  - <extended_thinking> 태그: Claude의 심층 탐색 (Agentic tasks)")
            print("="*70 + "\n")
            
            while True:
                try:
                    # 사용자 입력
                    user_input = input("\n👤 You: ").strip()
                    
                    if not user_input:
                        continue
                    
                    # 종료 명령
                    if user_input.lower() in ['quit', 'exit', 'q', 'bye']:
                        print("\n👋 AgentSUMO를 종료합니다.\n")
                        break
                    
                    # 상태 확인
                    if user_input.lower() == 'state':
                        state = agent.get_state()
                        print("\n📊 현재 상태:")
                        print(f"   Network: {state['simulation_state']['current_network'] or 'None'}")
                        print(f"   Routes: {state['simulation_state']['current_routes'] or 'None'}")
                        print(f"   대화 턴: {state['conversation_turns']}")
                        print(f"   도구: {state['tools_available']}개")
                        continue
                    
                    # 대화 리셋
                    if user_input.lower() == 'reset':
                        agent.reset_conversation()
                        print("\n🔄 대화 이력이 리셋되었습니다.")
                        continue
                    
                    # 도움말
                    if user_input.lower() == 'help':
                        print("\n💡 사용 예시:")
                        print("  - '안녕하세요!'")
                        print("  - 'SUMO가 무엇인가요?'")
                        print("  - '강남역 네트워크를 생성해주세요'")
                        print("  - '사용 가능한 도구는?'")
                        print("  - '평균 통행 시간을 분석해주세요'")
                        continue
                    
                    # AgentSUMO와 대화
                    print()
                    response = await agent.chat(user_input)
                    print(f"\n🤖 AgentSUMO:")
                    print("-" * 70)
                    print(response)
                    print("-" * 70)
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️  Ctrl+C 감지. 종료하려면 'quit' 입력\n")
                    continue
                
                except EOFError:
                    print("\n\n👋 AgentSUMO를 종료합니다.\n")
                    break
                
                except Exception as e:
                    print(f"\n❌ 오류 발생: {e}")
                    print("계속 대화할 수 있습니다.\n")
    
    except KeyboardInterrupt:
        print("\n\n👋 AgentSUMO를 종료합니다.\n")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Argument parsing
    parser = argparse.ArgumentParser(description='AgentSUMO CLI')
    parser.add_argument('--debug', action='store_true', 
                        help='Enable debug mode (show raw Claude responses)')
    args = parser.parse_args()
    
    print("\n🚀 AgentSUMO CLI 시작...\n")
    try:
        asyncio.run(main(debug=args.debug))
    except KeyboardInterrupt:
        print("\n\n👋 종료되었습니다.\n")
        sys.exit(0)

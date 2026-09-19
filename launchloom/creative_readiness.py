"""Read-only local integration report: configured is never reported as verified.

Run: python -m launchloom.creative_readiness
No provider request, executable, renderer or social publication is triggered.
"""
from __future__ import annotations
import json
import platform
import shutil
from .config import Settings
from .creative_assistant import capabilities


def readiness(settings: Settings) -> dict:
    ai=capabilities(settings)
    def entry(configured, note):
        return {'configured':bool(configured),'live_verified':False,'note':note}
    return {'schema_version':1,'operating_system':platform.system(),'read_only':True,
            'integrations':{
                'creative_ai':entry(ai['enabled'],'A real model response requires explicit data/charge consent.'),
                'vision_review':entry(ai['vision_enabled'],'Review the film before consenting to sampled-frame transfer.'),
                'paid_video':entry(settings.enable_paid_generation and settings.fal_key and settings.budget_usd>0,'Use the production board with an exact approved scene and budget; never blindly retry uncertain submissions.'),
                'after_effects_project':entry(settings.enable_after_effects and settings.afterfx_executable and platform.system()=='Windows','Automatic JSX project creation is currently implemented for Windows only.'),
                'after_effects_render':entry(settings.enable_after_effects and settings.aerender_executable,'Requires a licensed local installation and reviewed project. No executable was run.'),
                'social_publish':entry(settings.enable_live_publish and settings.postiz_base and settings.postiz_key,'Requires a reviewed account, exact copy/media, release, approval and remote publication verification.')},
            'local_tools':{'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe'))},
            'warning':'Configuration discovery is not a live integration test. No credentials are included.'}


if __name__=='__main__':
    from .cli import load_env
    load_env()
    print(json.dumps(readiness(Settings()),ensure_ascii=False,indent=2))

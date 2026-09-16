from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.auth_service import Session

router = APIRouter(prefix='/api/playback', tags=['Playback'])


class PlaybackOptions(BaseModel):
    audio_index: int | None = Field(default=None, ge=0)
    subtitle_index: int = Field(default=-1, ge=-1)
    start_ticks: int = Field(default=0, ge=0)
    max_bitrate: int = Field(default=20000000, ge=128000, le=140000000)
    media_source_id: str | None = None
    force_transcode: bool = False


class Progress(BaseModel):
    ItemId: str
    MediaSourceId: str
    PlaySessionId: str
    PositionTicks: int = Field(ge=0)
    IsPaused: bool = False
    IsMuted: bool = False
    VolumeLevel: int = Field(default=100, ge=0, le=100)
    PlayMethod: str = 'DirectPlay'
    LiveStreamId: str | None = None


@router.post('/{item_id}/info')
async def playback_info(item_id: str, options: PlaybackOptions, request: Request, session: Session):
    client = request.app.state.jellyfin
    body = {'UserId': session['user_id'], 'StartTimeTicks': options.start_ticks,
            'MaxStreamingBitrate': options.max_bitrate, 'AudioStreamIndex': options.audio_index,
            'SubtitleStreamIndex': options.subtitle_index, 'MediaSourceId': options.media_source_id,
            'IsPlayback': True, 'AutoOpenLiveStream': True,
            'EnableDirectPlay': not options.force_transcode, 'EnableDirectStream': not options.force_transcode,
            'EnableTranscoding': True,
            'DeviceProfile': {'Name': 'Jishflix Browser', 'MaxStreamingBitrate': options.max_bitrate,
                'DirectPlayProfiles': [
                    {'Container': 'mp4,m4v', 'Type': 'Video', 'VideoCodec': 'h264', 'AudioCodec': 'aac,mp3'},
                    {'Container': 'mp3,aac,m4a,flac,wav,ogg', 'Type': 'Audio'}],
                'TranscodingProfiles': [
                    {'Container': 'ts', 'Type': 'Video', 'Protocol': 'hls', 'VideoCodec': 'h264',
                     'AudioCodec': 'aac', 'Context': 'Streaming', 'MaxAudioChannels': '2',
                     'MinSegments': 2, 'BreakOnNonKeyFrames': True},
                    {'Container': 'mp3', 'Type': 'Audio', 'AudioCodec': 'mp3', 'Context': 'Streaming', 'Protocol': 'http'}],
                'SubtitleProfiles': [{'Format': 'vtt', 'Method': 'External'},
                                     {'Format': 'ass', 'Method': 'Encode'},
                                     {'Format': 'pgssub', 'Method': 'Encode'},
                                     {'Format': 'dvdsub', 'Method': 'Encode'}]}}
    info = await client.request('POST', f'Items/{item_id}/PlaybackInfo', session, body=body)
    sources = info.get('MediaSources', [])
    if not sources:
        raise HTTPException(422, info.get('ErrorCode') or 'No playable media source')
    source = next((s for s in sources if s['Id'] == options.media_source_id), sources[0])
    direct = bool(source.get('SupportsDirectPlay')) and not options.force_transcode
    if direct:
        media = 'Audio' if source.get('MediaStreams') and not any(s['Type'] == 'Video' for s in source['MediaStreams']) else 'Videos'
        url = f'{media}/{item_id}/stream?' + urlencode({'static': 'true', 'MediaSourceId': source['Id']})
    else:
        url = source.get('TranscodingUrl')
        if not url:
            raise HTTPException(422, 'Jellyfin could not negotiate a browser-compatible stream')
    subtitles = []
    for stream in source.get('MediaStreams', []):
        if stream.get('Type') == 'Subtitle' and stream.get('DeliveryMethod') == 'External':
            delivery = stream.get('DeliveryUrl')
            if delivery:
                subtitles.append({'index': stream['Index'], 'label': stream.get('DisplayTitle', 'Subtitles'),
                                  'language': stream.get('Language', 'und'), 'url': client.local_url(delivery)})
    return {'url': client.local_url(url), 'method': 'DirectPlay' if direct else 'Transcode',
            'play_session_id': info['PlaySessionId'], 'source_id': source['Id'],
            'live_stream_id': source.get('LiveStreamId'), 'streams': source.get('MediaStreams', []),
            'sources': [{'id': s['Id'], 'name': s.get('Name', s['Id'])} for s in sources],
            'subtitles': subtitles, 'start_ticks': options.start_ticks}


@router.post('/events/{event}', status_code=204)
async def progress(event: str, body: Progress, request: Request, session: Session):
    paths = {'start': 'Sessions/Playing', 'progress': 'Sessions/Playing/Progress', 'stop': 'Sessions/Playing/Stopped'}
    if event not in paths:
        raise HTTPException(404, 'Unknown playback event')
    client = request.app.state.jellyfin
    await client.request('POST', paths[event], session, body=body.model_dump(exclude_none=True))
    if event == 'stop':
        if body.LiveStreamId:
            await client.request('POST', 'LiveStreams/Close', session, params={'LiveStreamId': body.LiveStreamId})
        if body.PlayMethod == 'Transcode':
            await client.request('DELETE', 'Videos/ActiveEncodings', session,
                                 params={'DeviceId': session['device_id'], 'PlaySessionId': body.PlaySessionId})

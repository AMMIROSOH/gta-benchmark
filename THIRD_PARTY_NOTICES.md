# Third-party notices

The MIT license in this repository covers its original code and documentation.
Separately installed projects and game assets retain their own licenses and
notices. No GTA assets, SDK checkout, downloaded ASIs or FFmpeg binaries are
bundled in this source repository.

| Project | Use | Reference |
| --- | --- | --- |
| Plugin-SDK | Native SA structures, function wrappers and events | [Upstream](https://github.com/DK22Pac/plugin-sdk), [license](https://github.com/DK22Pac/plugin-sdk/blob/master/LICENSE) |
| SafetyHook | Native pad/device hooks through the SDK dependency | [Upstream](https://github.com/cursey/safetyhook), SDK's `safetyhook/LICENSE.txt` |
| gta-reversed | Reference for inspected device initialization, movement, menu and cutscene behavior | [Source](https://github.com/gta-reversed/gta-reversed) |
| III.VC.SA.WindowedMode | Separately installed local recording window | [Upstream](https://github.com/ThirteenAG/III.VC.SA.WindowedMode) |
| Ultimate ASI Loader | Existing loader recognized by the installer | [Upstream](https://github.com/ThirteenAG/Ultimate-ASI-Loader) |
| DXcam / comtypes / NumPy | Local capture and its runtime dependencies | [DXcam](https://github.com/ra1nty/DXcam), [comtypes](https://github.com/enthought/comtypes), [NumPy](https://numpy.org/) |
| FFmpeg | Silent local H.264 encoding | [Project](https://ffmpeg.org/), [Windows downloads](https://ffmpeg.org/download.html) |
| TypeSafe | Jev API service, separately authenticated | [API documentation](https://docs.typesafe.ai/api) |

The SDK baseline is commit `15f15b60bbf74c106e1b496ff92c98764abf4605`.
Plugin-SDK's license credits Dmitry K., fastman92 and LINK/2012 and uses the
zlib-style permission notice in its `LICENSE`. Keep upstream notices with any
redistributed dependency source or binaries.

The Windowed Mode installer pins v2.2 and SHA-256
`68039e974af4d0312281e5802fce8ef385b4291fbfc77a94229542fa57140b2a`.
Its README/changelog remain with the downloaded dependency on D:.

FFmpeg may be an existing system/Kdenlive installation or a publisher-checksummed
Gyan build. Bootstrap retains downloaded license/readme files and download
metadata beside that dependency. Use the notices belonging to the actual build
when redistributing it.

Grand Theft Auto and San Andreas are Rockstar Games titles. The user supplies
the game installation; this benchmark is a community integration.

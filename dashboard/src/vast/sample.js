// A self-contained InLine VAST 4.2 sample for the player. The MediaFile is a
// public MP4 (plays in any browser); the trackers point at the local mock DSP's
// same-origin pixel sink (/dsps/dsp-1/track), so "fire real pixels" during
// playback increments that DSP's tracked stats and is visible on the Dashboard.

export const SAMPLE_VAST = `<VAST version="4.2">
  <Ad id="sample-creative-1">
    <InLine>
      <AdSystem version="1.0">VoiseFakeDSP</AdSystem>
      <AdTitle>Voise Sample Creative</AdTitle>
      <Impression id="voisetech"><![CDATA[/dsps/dsp-1/track?ev=impression&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Impression>
      <Error><![CDATA[/dsps/dsp-1/track?ev=error&crid=sample-creative-1&code=[ERRORCODE]]]></Error>
      <Creatives>
        <Creative id="sample-creative-1" sequence="1">
          <UniversalAdId idRegistry="fakedsp.com">sample-creative-1</UniversalAdId>
          <Linear>
            <Duration>00:00:15</Duration>
            <TrackingEvents>
              <Tracking event="start"><![CDATA[/dsps/dsp-1/track?ev=start&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Tracking>
              <Tracking event="firstQuartile"><![CDATA[/dsps/dsp-1/track?ev=firstQuartile&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Tracking>
              <Tracking event="midpoint"><![CDATA[/dsps/dsp-1/track?ev=midpoint&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Tracking>
              <Tracking event="thirdQuartile"><![CDATA[/dsps/dsp-1/track?ev=thirdQuartile&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Tracking>
              <Tracking event="complete"><![CDATA[/dsps/dsp-1/track?ev=complete&crid=sample-creative-1&cb=[CACHEBUSTING]]]></Tracking>
            </TrackingEvents>
            <VideoClicks>
              <ClickThrough id="fakedsp"><![CDATA[https://voisetech.com/]]></ClickThrough>
              <ClickTracking><![CDATA[/dsps/dsp-1/track?ev=click&crid=sample-creative-1&cb=[CACHEBUSTING]]]></ClickTracking>
            </VideoClicks>
            <MediaFiles>
              <MediaFile delivery="progressive" type="video/mp4" width="1280" height="720" bitrate="1000" scalable="true" maintainAspectRatio="true"><![CDATA[https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4]]></MediaFile>
            </MediaFiles>
          </Linear>
        </Creative>
      </Creatives>
    </InLine>
  </Ad>
</VAST>`

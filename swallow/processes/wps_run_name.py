from pywps import Process
from pywps import ComplexOutput, Format
from pywps import LiteralInput, LiteralOutput, BoundingBoxInput
from pywps.exceptions import InvalidParameterValue
from pywps.app.Common import Metadata
from pywps.inout.literaltypes import AllowedValue
from pywps.validator.mode import MODE

from swallow.run_name import run_name
from datetime import timedelta

import logging
LOGGER = logging.getLogger('PYWPS')


class RunNAME(Process):
    """
    Notes
    -----

    This process runs NAME on JASMIN with the user providing all parameters including the name of the job.
    """
    def __init__(self):
        inputs = [
            LiteralInput('title', 'Title', data_type='string',
                         abstract='Title of job'),
            LiteralInput('longitude', 'Longitude', data_type='float',
                         abstract='Longitude of release'),
            LiteralInput('latitude', 'Latitude', data_type='float',
                         abstract='Latitude of release'),
            LiteralInput('elevation', 'Elevation', data_type='integer',
                         abstract='Elevation of release, m agl for land, m asl for marine release',
                         default=10, min_occurs=0),
            # LiteralInput('elevation_range_min','Elevation Range Min', data_type='integer',
            #              abstract='Minimum range of elevation',
            #              default=None, min_occurs=0),
            # LiteralInput('elevation_range_max', 'Elevation Range Max', data_type='integer',
            #              abstract = 'Maximum range of elevation',
            #              default=None, min_occurs=0),
            LiteralInput('runBackwards', 'Run Backwards', data_type='boolean',
                         abstract = 'Whether to run backwards in time or forwards',
                         default = '1', min_occurs=0),
            LiteralInput('time', 'Time to run model over', data_type='integer',
                         abstract = '',
                         default=1),
            LiteralInput('timeFmt',' ', data_type='string',
                         abstract='number of days/hours NAME will run over. Maximum is 20 days.',
                         allowed_values = ['days','hours'], default='days'),
            # bbox not working:
            # BoundingBoxInput('domain', 'Computational Domain', crss=['epsg:4326'],
            #                  abstract='Coordinates to run NAME within',
            #                  min_occurs=1),
            # Temporary bbox solution:
            LiteralInput('min_lon', 'Minimum longitude',
                         abstract='Minimum longitude for plot boundary. Note that reducing the size of the bounds will speed up the run-time of the process.',
                         data_type='float',
                         default=-180,
                         min_occurs=1),
            LiteralInput('max_lon', 'Maximum longitude',
                         abstract='Maximum longitude for plot boundary. Note that reducing the size of the bounds will speed up the run-time of the process.',
                         data_type='float',
                         default=180,
                         min_occurs=1),
            LiteralInput('min_lat', 'Minimum latitude',
                         abstract='Minimum latitude for plot boundary. Note that reducing the size of the bounds will speed up the run-time of the process.',
                         data_type='float',
                         default=-90,
                         min_occurs=1),
            LiteralInput('max_lat', 'Maximum latitude',
                         abstract='Maximum latitude for plot boundary. Note that reducing the size of the bounds will speed up the run-time of the process.',
                         data_type='float',
                         default=90,
                         min_occurs=1),
            LiteralInput('elevationOut', 'Output elevation averaging range(s)', data_type='string',
                         abstract='Elevation range where the particle number is counted (m agl)'
                                  ' Example: 0-100',
                         default='0-100', min_occurs=1, max_occurs=4),
            LiteralInput('resolution','Resolution', data_type='float',
                         abstract='degrees, note the UM global Met data was only 17Km resolution',
                         allowed_values=[0.05,0.25], default=0.25, min_occurs=0),
            LiteralInput('timestamp','Run Type', data_type='string',
                         abstract='how often NAME will run',
                         allowed_values=['3-hourly','daily']),
            LiteralInput('dailytime','Daily run time (UTC)', data_type='time',
                         abstract='if running daily, at what time will it run',
                         min_occurs = 0),
            LiteralInput('dailyreleaselen', 'Daily release length', data_type='integer',
                         abstract='if running daily, over how many hours will it release?',
                         allowed_values=[1, 3, 6, 12, 24], min_occurs=0),
            LiteralInput('startdate', 'Start date', data_type='dateTime',
                         abstract='UTC start date of runs'),
            LiteralInput('enddate', 'End date', data_type='dateTime',
                         abstract = 'UTC end date of runs (inclusive)'),
            ]
        outputs = [
            LiteralOutput('runid', 'Run ID', data_type='string',
                          abstract='Unique run identifier, this is needed to create plots'),
            ComplexOutput('FileContents', 'Output files (zipped)',
                          abstract='Output files (zipped)',
                          supported_formats=[Format('application/x-zipped-shp')],
                          as_reference=True),
            ComplexOutput('SummaryPlot', 'Summary Plot',
                          abstract='Summary plot of whole time period',
                          supported_formats=[Format('image/tiff')],
                          as_reference=True),
            ]

        super(RunNAME, self).__init__(
            self._handler,
            identifier='run_name',
            title='Run NAME',
            abstract='Run NAME on JASMIN using user-defined release location and bounding box.',
            version='0.1',
            metadata=[
                Metadata('NAME-on-JASMIN guide', 'http://jasmin.ac.uk/jasmin-users/stories/processing/'),
                Metadata('Process image', 'https://name-staging.ceda.ac.uk/static/phoenix/img/NAME_banner_dark.png', 'http://www.opengis.net/spec/wps/2.0/def/process/description/media'),
            ],
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True)

    def _handler(self, request, response):

        # Need to process the elevationOut inputs from a list of strings, into an array of tuples.
        ranges = []
        for elevation_range in request.inputs['elevationOut']:
            ranges.append(self.translate_elevation(elevation_range.data))

        domains = []

        # Throw manually with temporary bbox solution
        if request.inputs['min_lon'][0].data < -180:
            raise InvalidParameterValue('Bounding box minimum longitude input cannot be below -180')
        if request.inputs['max_lon'][0].data > 180:
            raise InvalidParameterValue('Bounding box maximum longitude input cannot be above 180')
        if request.inputs['min_lat'][0].data < -90:
            raise InvalidParameterValue('Bounding box minimum latitude input cannot be below -90')
        if request.inputs['max_lat'][0].data > 90:
            raise InvalidParameterValue('Bounding box minimum latitude input cannot be above 90')

        # Add manually with temporary bbox solution
        domains.append(request.inputs['min_lat'][0].data)
        domains.append(request.inputs['min_lon'][0].data)
        domains.append(request.inputs['max_lat'][0].data)
        domains.append(request.inputs['max_lon'][0].data)

        # Don't add automatically as bbox not working
        # for val in request.inputs['domain'][0].data:
        #     domains.append(float(val))

        # If min_lon and max_lon are 180, need to reset to 179.9
        if domains[1] == -180 and domains[3] == 180:
            domains[1] = -179.875
            domains[3] = 179.9

        params = dict()
        for p in request.inputs:
            if p == 'elevationOut':
                params[p] = ranges
            # Don't assign automatically as bbox not working
            # elif p == 'domain':
            #     params[p] = domains
            else:
                params[p] = request.inputs[p][0].data
            
        # Assign manually with temporary bbox solution
        params['domain'] = domains

        # Need to test start and end dates make sense relative to each other
        if params['startdate'] >= params['enddate'] + timedelta(days=1):
            raise InvalidParameterValue('The end date is earlier than the start date!')

        if (params['enddate'] + timedelta(days=1)) - params['startdate'] >= timedelta(days=93):
            raise InvalidParameterValue('Can only run across a maximum of three months in one go')

        # Need to test we don't run too far backwards/forwards
        if params['timeFmt'] == 'days':
            if params['time'] > 20:
                raise InvalidParameterValue('Can only run NAME over a maximum of 20 days forwards/backwards')
        else:
            if params['time'] > 20 * 24:
                raise InvalidParameterValue('Can only run NAME over a maximum of 20 days forwards/backwards')

        response.update_status('Processed parameters', 5)

        outdir, zippedfile, mapfile = run_name(params, response)

        response.outputs['FileContents'].file = zippedfile + '.zip'
        response.outputs['runid'].data = outdir
        response.outputs['SummaryPlot'].file = mapfile

        response.update_status('done', 100)
        return response

    def translate_elevation(self, elevation_range):
        if '-' not in elevation_range:
            raise InvalidParameterValue(
                f'The value "{elevation_range}" does not contain a "-" character to define a range, e.g. 0-100')
        mini, maxi = elevation_range.split('-')
        try:
            mini = int(mini)
            maxi = int(maxi)
        except ValueError:
            raise InvalidParameterValue(f'The value {elevation_range} is incorrect: cannot find two numbers')
        if mini >= maxi:
            raise InvalidParameterValue(f'The value {elevation_range} is incorrect: minimum is not less than maximum')
        if mini < 0 or maxi < 0:
            raise InvalidParameterValue(f'The value {elevation_range} is incorrect: Entire range must be above 0')
        return mini, maxi

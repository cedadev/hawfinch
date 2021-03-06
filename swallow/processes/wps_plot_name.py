from pywps import Process
from pywps import ComplexOutput, Format, FORMATS
from pywps import LiteralInput, BoundingBoxInput
from pywps.app.Common import Metadata
from pywps.exceptions import InvalidParameterValue
from pywps.inout.literaltypes import AllowedValue
from pywps.validator.mode import MODE

from pynameplot import Name, drawMap, Sum
from pynameplot.namereader import util

from datetime import datetime
import shutil
import os
import calendar
import glob
import tempfile
from swallow.utils import getjasminconfigs, get_num_dates
from dateutil.parser import parse

import logging
LOGGER = logging.getLogger('PYWPS')


class PlotNAME(Process):
    """
    Notes
    -----

    This process takes the output of a previous NAME job and plots the outputs with user defined parameters. 
    """
    def __init__(self):
        inputs = [
            LiteralInput('filelocation', 'NAME run ID', data_type='string',
                         abstract='Run ID that identifies the NAME output files'),
            LiteralInput('summarise', 'Summarise data', data_type='string',
                         abstract='Plot summaries of each day/week/month',
                         allowed_values=['NA', 'day', 'week', 'month', 'all'], default='NA'),
            LiteralInput('timestamp', 'Plot specific date and time', data_type='dateTime',
                         abstract='Plot only a specific timestamp. Excludes the creation of summary plots. '
                                  'Format: YYYY-MM-DD HH:MM:SSZ',
                         min_occurs=0),
            LiteralInput('station', 'Mark release location', data_type='boolean',
                         abstract='Mark the location of release onto the image',
                         min_occurs=0),
            LiteralInput('projection', 'Projection', data_type='string',
                         abstract='Map projection', allowed_values=['cyl', 'npstere', 'spstere'], min_occurs=0),
            # bbox not working:
            # BoundingBoxInput('domain', 'Computational Domain', crss=['epsg:4326'],
            #                  abstract='Coordinates to plot within',
            #                  min_occurs=0),
            # Temporary bbox solution
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
            LiteralInput('scale', 'Particle concentration scale', data_type='string',
                         abstract='Particle concentration scale. If no value is set, it will autoscale. '
                                  'Format: Min,Max',
                         min_occurs=0),
            LiteralInput('colormap', 'Colour map', data_type='string',
                         abstract='Matplotlib color map name', default='coolwarm', min_occurs=0,
                         allowed_values=['coolwarm', 'viridis', 'rainbow']),
            ]
        outputs = [
            ComplexOutput('FileContents', 'Plot file(s)',
                          abstract='Plot files',
                          supported_formats=[Format('application/x-zipped-shp'),
                                             Format('text/plain'),
                                             Format('image/png'),
                                             FORMATS.GEOTIFF],
                          as_reference=True),
            ]

        super(PlotNAME, self).__init__(
            self._handler,
            identifier='plot_name',
            title='Plot NAME results',
            abstract='Generate plots from a completed NAME job.',
            version='0.1',
            metadata=[
                Metadata('NAME-on-JASMIN guide', 'http://jasmin.ac.uk/jasmin-users/stories/processing/'),
                Metadata('Colour maps', 'https://matplotlib.org/users/colormaps.html'),
                Metadata('Process image', 'https://name-staging.ceda.ac.uk/static/phoenix/img/NAME_banner_dark.png', 'http://www.opengis.net/spec/wps/2.0/def/process/description/media'),
            ],
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True)

    def _handler(self, request, response):

        jasconfigs = getjasminconfigs()
        rundir = os.path.join(jasconfigs.get('jasmin', 'outputdir'), request.inputs['filelocation'][0].data)
        LOGGER.debug('Working Directory for plots: %s' % rundir)

        # Parse NAME run input params
        inputs = {}
        with open(os.path.join(rundir, 'user_input_parameters.txt'), 'r') as ins:
            for l in ins:
                data = l.rstrip().split(': ')
                inputs[data[0]] = data[1]

        # Throw manually with temporary bbox solution
        if request.inputs['min_lon'][0].data < -180:
            raise InvalidParameterValue('Bounding box minimum longitude input cannot be below -180')
        if request.inputs['max_lon'][0].data > 180:
            raise InvalidParameterValue('Bounding box maximum longitude input cannot be above 180')
        if request.inputs['min_lat'][0].data < -90:
            raise InvalidParameterValue('Bounding box minimum latitude input cannot be below -90')
        if request.inputs['max_lat'][0].data > 90:
            raise InvalidParameterValue('Bounding box minimum latitude input cannot be above 90')


        # Parse input params into plot options
        plotoptions = {}
        # When using bbox:
        # plotoptions['lon_bounds'] = (int(float(request.inputs['domain'][0].data[1])), int(float(request.inputs['domain'][0].data[3])))
        # plotoptions['lat_bounds'] = (int(float(request.inputs['domain'][0].data[0])), int(float(request.inputs['domain'][0].data[2])))
        # When using temporary bbox solution
        plotoptions['lon_bounds'] = (int(request.inputs['min_lon'][0].data), int(request.inputs['max_lon'][0].data))
        plotoptions['lat_bounds'] = (int(request.inputs['min_lat'][0].data), int(request.inputs['max_lat'][0].data))

        plotoptions['outdir'] = os.path.join(rundir, 'plots_{}'.format(datetime.strftime(datetime.now(), '%s')))
        for p in request.inputs:
            # When using bbox
            # if p == 'timestamp' or p == 'filelocation' or p == 'summarise' or p == 'domain':
            # When using temporary bbox solution
            if p == 'timestamp' or p == 'filelocation' or p == 'summarise' or p == 'min_lon' or p == 'max_lon' or p == 'min_lat' or p == 'max_lat':
                continue
            elif p == 'scale':
                statcoords = request.inputs[p][0].data.split(',')
                plotoptions[p] = (float(statcoords[0].strip()), float(statcoords[1].strip()))
            elif p == 'station' and request.inputs[p][0].data == True:
                plotoptions[p] = (float(inputs['longitude']), float(inputs['latitude']))
            else:
                plotoptions[p] = request.inputs[p][0].data

        files = glob.glob(os.path.join(rundir, 'outputs', '*_group*.txt'))
        if len(files) == 0:
            raise InvalidParameterValue('Unable to find any output files. File names must be named "*_group*.txt"')

        if 'timestamp' in request.inputs:
            request.inputs['summarise'][0].data = 'NA'

        LOGGER.debug('Plot options: %s' % plotoptions)

        response.update_status('Processed plot parameters', 5)

        tot_plots = get_num_dates(start=datetime.date(parse(inputs['startdate'])),
                                  end=datetime.date(parse(inputs['enddate'])),
                                  sum=request.inputs['summarise'][0].data,
                                  type=inputs['timestamp'])

        # We need to find all the groups and loop through them one at a time!
        groups = {}
        for filename in os.listdir(os.path.join(rundir, 'outputs')):
            if not filename.endswith('txt'):
                continue
            groupnum = filename[14]
            try:
                groupnum = int(groupnum)
            except:
                raise Exception('Cannot identify groupnumber %s' % groupnum)

            if groupnum in groups:
                shutil.copy(os.path.join(rundir, 'outputs', filename), groups[groupnum])
            else:
                groups[groupnum] = tempfile.mkdtemp()
                shutil.copy(os.path.join(rundir, 'outputs', filename), groups[groupnum])

        ngroups = len(groups)
        tot_plots = tot_plots * ngroups
        plots_made = 0

        response.update_status('Plotting', 10)

        oldper = 10

        for groupnum, tmpdir in sorted(groups.items()):
            if request.inputs['summarise'][0].data != 'NA':
                s = Sum(tmpdir)

            if request.inputs['summarise'][0].data == 'week':
                for week in range(1, 53):
                    s.sumWeek(week)
                    if len(s.files) == 0:
                        LOGGER.debug('No files found for week %s' % week)
                        continue
                    plotoptions['caption'] = '{} {} {} {}: {} week {} sum (UTC)'.format(s.runname, s.averaging,
                                                                                        s.altitude, s.direction,
                                                                                        s.year, week)
                    plotoptions['outfile'] = '{}_{}_{}_{}_weekly.png'.format(s.runname, s.altitude.strip('()'),
                                                                             s.year, week)
                    try:
                        drawMap(s, 'total', **plotoptions)
                        LOGGER.debug('Plotted %s' % plotoptions['outfile'])
                    except:
                        LOGGER.error('Failed to plot %s' % plotoptions['outfile'])
                    plots_made += 1
                    newper = 10+int((plots_made/float(tot_plots))*85)
                    if oldper != newper:
                        response.update_status('Plotting', newper)
                        oldper = newper

            elif request.inputs['summarise'][0].data == 'month':
                for month in range(1, 13):
                    s.sumMonth(str(month))
                    if len(s.files) == 0:
                        LOGGER.debug('No files found for month %s' % month)
                        continue
                    plotoptions['caption'] = '{} {} {} {}: {} {} sum (UTC)'.format(s.runname, s.averaging, s.altitude,
                                                                             s.direction, s.year,
                                                                             calendar.month_name[month])
                    plotoptions['outfile'] = '{}_{}_{}_{}_monthly.png'.format(s.runname, s.altitude.strip('()'),
                                                                              s.year, month)
                    try:
                        drawMap(s, 'total', **plotoptions)
                        LOGGER.debug('Plotted %s' % plotoptions['outfile'])
                    except:
                        LOGGER.error('Failed to plot %s' % plotoptions['outfile'])
                    plots_made += 1
                    newper = 10 + int((plots_made / float(tot_plots)) * 85)
                    if oldper != newper:
                        response.update_status('Plotting', newper)
                        oldper = newper

            elif request.inputs['summarise'][0].data == 'all':
                s.sumAll()
                plotoptions['caption'] = '{} {} {} {}: Summed (UTC)'.format(s.runname, s.averaging, s.altitude,
                                                                            s.direction)
                plotoptions['outfile'] = '{}_{}_summed_all.png'.format(s.runname, s.altitude.strip('()'))#TODO: Copy to plot all
                #TODO: Fix: Currently all levels plotted with same name and overwritten, bug?
                # Happening because of: https://github.com/TeriForey/pyNAMEplot/blob/master/pynameplot/namereader/name.py#L151
                # Is is this correct or an assumption?
                # If correct then maybe text input should be a string list
                try:
                    drawMap(s, 'total', **plotoptions)
                    LOGGER.debug('Plotted %s' % plotoptions['outfile'])
                except:
                    LOGGER.error('Failed to plot %s' % plotoptions['outfile'])
                plots_made += 1
                newper = 10 + int((plots_made / float(tot_plots)) * 85)
                if oldper != newper:
                    response.update_status('Plotting', newper)
                    oldper = newper
            else:
                for filename in os.listdir(tmpdir):
                    if '_group' in filename and filename.endswith('.txt'):
                        if request.inputs['summarise'][0].data == 'day':
                            #s = Sum(tmpdir)
                            date = util.shortname(filename)
                            s.sumDay(date)
                            plotoptions['caption'] = '{} {} {} {}: {}{}{} day sum (UTC)'.format(s.runname, s.averaging,
                                                                                          s.altitude, s.direction,
                                                                                          s.year, s.month, s.day)
                            plotoptions['outfile'] = '{}_{}_{}{}{}_daily.png'.format(s.runname, s.altitude.strip('()'),
                                                                                     s.year, s.month, s.day)
                            try:
                                drawMap(s, 'total', **plotoptions)
                                LOGGER.debug('Plotted %s' % plotoptions['outfile'])
                            except:
                                LOGGER.error('Failed to plot %s' % plotoptions['outfile'])
                            plots_made += 1
                            newper = 10 + int((plots_made / float(tot_plots)) * 85)
                            if oldper != newper:
                                response.update_status('Plotting', newper)
                                oldper = newper
                        elif request.inputs['summarise'][0].data == 'NA':
                            n = Name(os.path.join(tmpdir, filename))
                            if 'timestamp' in request.inputs:
                                timestamp = datetime.strftime(request.inputs['timestamp'][0].data, '%d/%m/%Y %H:%M UTC')
                                LOGGER.debug('Reformatted time: %s' % timestamp)
                                if timestamp in n.timestamps:
                                    try:
                                        drawMap(n, timestamp, **plotoptions)
                                        LOGGER.debug('Plotted %s' % timestamp)
                                    except:
                                        LOGGER.error('Failed to plot %s' % timestamp)
                                    plots_made += 1
                                    newper = 10 + int((plots_made / float(tot_plots)) * 85)
                                    if oldper != newper:
                                        response.update_status('Plotting', newper)
                                        oldper = newper
                                    break
                            else:
                                for column in n.timestamps:
                                    try:
                                        drawMap(n, column, **plotoptions)
                                        LOGGER.debug('Plotted %s' % column)
                                    except:
                                        LOGGER.error('Failed to plot %s' % column)
                                    plots_made += 1
                                    newper = 10 + int((plots_made / float(tot_plots)) * 85)
                                    if oldper != newper:
                                        response.update_status('Plotting', newper)
                                        oldper = newper

            # Finished plotting so will now delete temp directory
            shutil.rmtree(tmpdir)

        # Outputting different response based on the number of plots generated
        response.update_status('Formatting output', 95)
        if not os.path.exists(plotoptions['outdir']):
            LOGGER.debug('Did not create any plots')
            response.outputs['FileContents'].data_format = FORMATS.TEXT
            response.outputs['FileContents'].data = 'No plots created, check input options'
        else:
            if len(os.listdir(plotoptions['outdir'])) == 1:
                LOGGER.debug('Only one output plot')
                response.outputs['FileContents'].data_format = Format('image/png')
                response.outputs['FileContents'].file = os.path.join(plotoptions['outdir'],
                                                                     os.listdir(plotoptions['outdir'])[0])
            else:
                zippedfile = '{}_plots'.format(request.inputs['filelocation'][0].data)
                shutil.make_archive(zippedfile, 'zip', plotoptions['outdir'])
                LOGGER.debug('Zipped file: %s (%s bytes)' % (zippedfile+'.zip', os.path.getsize(zippedfile+'.zip')))
                response.outputs['FileContents'].data_format = FORMATS.SHP
                response.outputs['FileContents'].file = zippedfile + '.zip'

        response.update_status('done', 100)
        return response

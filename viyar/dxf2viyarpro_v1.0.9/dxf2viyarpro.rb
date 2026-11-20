require 'sketchup.rb'
require 'extensions.rb'
require 'json'

module VP
  module DXF

    unless file_loaded?(__FILE__)

      languages_file_path = File.expand_path('../dxf2viyarpro/Resources/languages.json', __FILE__)
      languages_string = File.read(languages_file_path)
      parsed_languages = JSON.parse(languages_string)
      language = Sketchup.os_language

      @@lang = if language == "ru" || language == "uk"
                 parsed_languages["UKRAINIAN"]
               else
                 parsed_languages["ENGLISH"]
               end

      def self.lang
        @@lang
      end

      ex = SketchupExtension.new('DXF2VIYARPRO', 'dxf2viyarpro/main')
      ex.description = @@lang["Export DXF for ViyarPro."]
      ex.version     = '1.0.9'
      ex.copyright   = 'ViyarPro © 2025'
      ex.creator     = 'ViyarPro'
      Sketchup.register_extension(ex, true)
      file_loaded(__FILE__)
    end

  end
end
